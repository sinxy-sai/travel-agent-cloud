from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agent_engines.tool_tracing import TracingTravelToolProvider
from app.agent_engines.types import (
    TravelAgentEngineCapabilities,
    TravelAgentNodeEvent,
    TravelAgentRunTrace,
    TravelAgentToolCall,
)
from app.llm import LLMClient
from app.planning_context import build_travel_planning_context
from app.planner import build_mock_regenerated_trip_day, build_mock_trip_plan, enrich_trip_plan_response
from app.schemas import AgentMode, ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider

MAX_TRACE_HISTORY = 10


class BasicTravelAgentEngine:
    def __init__(self, settings: Settings, travel_tools: TravelToolProvider, name: str = "basic") -> None:
        self.name = name
        self._llm_client = LLMClient(settings)
        self._travel_tools = travel_tools
        self._last_run_trace: TravelAgentRunTrace | None = None
        self._recent_run_traces: list[TravelAgentRunTrace] = []

    @property
    def llm_enabled(self) -> bool:
        return self._llm_client.enabled

    @property
    def capabilities(self) -> TravelAgentEngineCapabilities:
        return TravelAgentEngineCapabilities(
            supports_chat=True,
            supports_trip_planning=True,
            supports_day_regeneration=True,
            workflow_nodes=("request_context", "llm_call", "tool_enrichment", "mock_fallback"),
            dependency_mode="builtin",
        )

    @property
    def last_run_trace(self) -> TravelAgentRunTrace | None:
        return self._last_run_trace

    @property
    def recent_run_traces(self) -> tuple[TravelAgentRunTrace, ...]:
        return tuple(self._recent_run_traces)

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        started_at = _utc_timestamp()
        started = perf_counter()
        llm_response = self._llm_client.generate_chat_reply(messages, request.mode)
        fallback_used = not bool(llm_response)
        response = llm_response or _build_rule_based_reply(request)
        self._record_trace(self._build_trace(
            operation="chat",
            completed_nodes=("llm_call", "mock_fallback") if fallback_used else ("llm_call",),
            fallback_used=fallback_used,
            node_events=(
                _node_event("llm_call", "SKIPPED", "llm_disabled_or_empty_response")
                if fallback_used
                else _node_event("llm_call", "SUCCEEDED", "chat_reply_generated"),
                _node_event("mock_fallback", "FALLBACK", "rule_based_reply")
                if fallback_used
                else _node_event("mock_fallback", "SKIPPED", "llm_response_available"),
            ),
            tool_calls=(),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        started_at = _utc_timestamp()
        started = perf_counter()
        tool_calls: list[TravelAgentToolCall] = []
        traced_tools = TracingTravelToolProvider(self._travel_tools, tool_calls)
        planning_context = build_travel_planning_context(request)
        context_event = _node_event("request_context", "SUCCEEDED", planning_context.to_trace_detail())
        llm_response = self._llm_client.generate_trip_plan(request, planning_context)
        if llm_response:
            response = enrich_trip_plan_response(llm_response, request, traced_tools, planning_context)
            self._record_trace(self._build_trace(
                operation="trip_plan",
                completed_nodes=("request_context", "llm_call", "tool_enrichment"),
                fallback_used=False,
                node_events=(
                    context_event,
                    _node_event("llm_call", "SUCCEEDED", "trip_plan_json_generated"),
                    _node_event("tool_enrichment", "SUCCEEDED", "travel_tools_applied"),
                    _node_event("mock_fallback", "SKIPPED", "llm_plan_available"),
                ),
                tool_calls=tuple(tool_calls),
                started_at=started_at,
                duration_ms=_elapsed_ms(started),
            ))
            return response
        response = build_mock_trip_plan(request, traced_tools, planning_context)
        self._record_trace(self._build_trace(
            operation="trip_plan",
            completed_nodes=("request_context", "llm_call", "mock_fallback"),
            fallback_used=True,
            node_events=(
                context_event,
                _node_event("llm_call", "SKIPPED", "llm_disabled_or_invalid_response"),
                _node_event("tool_enrichment", "SKIPPED", "no_llm_plan_to_enrich"),
                _node_event("mock_fallback", "FALLBACK", "mock_trip_plan_generated"),
            ),
            tool_calls=tuple(tool_calls),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        started_at = _utc_timestamp()
        started = perf_counter()
        regenerated_day = self._llm_client.regenerate_trip_day(
            saved_trip_plan,
            day,
            instruction,
        )
        fallback_used = regenerated_day is None
        response = regenerated_day or build_mock_regenerated_trip_day(saved_trip_plan, day, instruction)
        self._record_trace(self._build_trace(
            operation="day_regeneration",
            completed_nodes=("llm_call", "mock_fallback") if fallback_used else ("llm_call",),
            fallback_used=fallback_used,
            node_events=(
                _node_event("llm_call", "SKIPPED", "llm_disabled_or_invalid_response")
                if fallback_used
                else _node_event("llm_call", "SUCCEEDED", "day_json_generated"),
                _node_event("mock_fallback", "FALLBACK", "mock_day_generated")
                if fallback_used
                else _node_event("mock_fallback", "SKIPPED", "llm_day_available"),
            ),
            tool_calls=(),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def _record_trace(self, trace: TravelAgentRunTrace) -> None:
        self._last_run_trace = trace
        self._recent_run_traces.insert(0, trace)
        del self._recent_run_traces[MAX_TRACE_HISTORY:]

    def _build_trace(
        self,
        operation: str,
        completed_nodes: tuple[str, ...],
        fallback_used: bool,
        node_events: tuple[TravelAgentNodeEvent, ...],
        tool_calls: tuple[TravelAgentToolCall, ...],
        started_at: str,
        duration_ms: int,
    ) -> TravelAgentRunTrace:
        return TravelAgentRunTrace(
            run_id=str(uuid4()),
            operation=operation,
            engine_name=self.name,
            started_at=started_at,
            duration_ms=duration_ms,
            workflow_nodes=self.capabilities.workflow_nodes,
            completed_nodes=completed_nodes,
            fallback_used=fallback_used,
            llm_enabled=self.llm_enabled,
            node_events=node_events,
            tool_calls=tool_calls,
        )


def _build_rule_based_reply(request: ChatRequest) -> str:
    message = request.message.strip()
    if request.mode == AgentMode.TRIP_PLANNING:
        return (
            "I can turn this travel requirement into a structured itinerary. "
            f"Current request: {message}. "
            "Next I will collect destination, days, budget, interests, and constraints before calling trip planning tools."
        )

    return (
        "I received your travel question and created a conversation context. "
        f"You said: {message}. "
        "The current runtime is rule-based; LLM planning and tool calls will be added behind this contract."
    )


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _node_event(node_name: str, status: str, detail: str) -> TravelAgentNodeEvent:
    return TravelAgentNodeEvent(node_name=node_name, status=status, detail=detail)

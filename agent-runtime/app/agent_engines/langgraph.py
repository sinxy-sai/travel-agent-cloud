from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agent_engines.types import TravelAgentEngineCapabilities, TravelAgentNodeEvent, TravelAgentRunTrace
from app.llm import LLMClient
from app.planner import build_mock_regenerated_trip_day, build_mock_trip_plan, enrich_trip_plan_response
from app.schemas import AgentMode, ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider

MAX_TRACE_HISTORY = 10


@dataclass
class ChatWorkflowState:
    request: ChatRequest
    messages: list[ChatMessage]
    response: str | None = None
    fallback_used: bool = False


@dataclass
class TripPlanningWorkflowState:
    request: TripPlanRequest
    draft_plan: TripPlanResponse | None = None
    final_plan: TripPlanResponse | None = None
    fallback_used: bool = False


@dataclass
class DayRegenerationWorkflowState:
    saved_trip_plan: SavedTripPlan
    day: int
    instruction: str
    regenerated_day: TripDay | None = None
    fallback_used: bool = False


class LangGraphTravelAgentEngine:
    """Graph-shaped engine skeleton for the future LangGraph implementation.

    This class intentionally avoids importing LangGraph for now. The methods are
    structured as graph nodes so the future implementation can replace the
    sequential runner with a compiled LangGraph without changing public APIs.
    """

    name = "langgraph:workflow-skeleton"

    def __init__(self, settings: Settings, travel_tools: TravelToolProvider) -> None:
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
            workflow_nodes=(
                "chat_llm",
                "chat_fallback",
                "trip_draft",
                "trip_enrichment",
                "trip_validation",
                "day_regeneration",
                "day_fallback",
            ),
            dependency_mode="dependency-free-skeleton",
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
        state = ChatWorkflowState(request=request, messages=messages)
        state = self._chat_llm_node(state)
        state = self._chat_fallback_node(state)
        response = state.response or _build_rule_based_reply(request)
        self._record_trace(self._build_trace(
            operation="chat",
            completed_nodes=("chat_llm", "chat_fallback"),
            fallback_used=state.fallback_used,
            node_events=_chat_node_events(state),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        started_at = _utc_timestamp()
        started = perf_counter()
        state = TripPlanningWorkflowState(request=request)
        state = self._trip_draft_node(state)
        state = self._trip_enrichment_node(state)
        state = self._trip_validation_node(state)
        response = state.final_plan or build_mock_trip_plan(request, self._travel_tools)
        self._record_trace(self._build_trace(
            operation="trip_plan",
            completed_nodes=("trip_draft", "trip_enrichment", "trip_validation"),
            fallback_used=state.fallback_used,
            node_events=_trip_node_events(state),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        started_at = _utc_timestamp()
        started = perf_counter()
        state = DayRegenerationWorkflowState(
            saved_trip_plan=saved_trip_plan,
            day=day,
            instruction=instruction,
        )
        state = self._day_regeneration_node(state)
        state = self._day_fallback_node(state)
        response = state.regenerated_day or build_mock_regenerated_trip_day(saved_trip_plan, day, instruction)
        self._record_trace(self._build_trace(
            operation="day_regeneration",
            completed_nodes=("day_regeneration", "day_fallback"),
            fallback_used=state.fallback_used,
            node_events=_day_node_events(state),
            started_at=started_at,
            duration_ms=_elapsed_ms(started),
        ))
        return response

    def _chat_llm_node(self, state: ChatWorkflowState) -> ChatWorkflowState:
        response = self._llm_client.generate_chat_reply(state.messages, state.request.mode)
        return ChatWorkflowState(request=state.request, messages=state.messages, response=response)

    def _chat_fallback_node(self, state: ChatWorkflowState) -> ChatWorkflowState:
        if state.response:
            return state
        return ChatWorkflowState(
            request=state.request,
            messages=state.messages,
            response=_build_rule_based_reply(state.request),
            fallback_used=True,
        )

    def _trip_draft_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        draft_plan = self._llm_client.generate_trip_plan(state.request)
        return TripPlanningWorkflowState(request=state.request, draft_plan=draft_plan)

    def _trip_enrichment_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        if not state.draft_plan:
            return state
        final_plan = enrich_trip_plan_response(state.draft_plan, state.request, self._travel_tools)
        return TripPlanningWorkflowState(
            request=state.request,
            draft_plan=state.draft_plan,
            final_plan=final_plan,
            fallback_used=state.fallback_used,
        )

    def _trip_validation_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        if not state.final_plan or not state.final_plan.days:
            fallback_plan = build_mock_trip_plan(state.request, self._travel_tools)
            return TripPlanningWorkflowState(
                request=state.request,
                draft_plan=state.draft_plan,
                final_plan=fallback_plan,
                fallback_used=True,
            )
        return state

    def _day_regeneration_node(self, state: DayRegenerationWorkflowState) -> DayRegenerationWorkflowState:
        regenerated_day = self._llm_client.regenerate_trip_day(
            state.saved_trip_plan,
            state.day,
            state.instruction,
        )
        return DayRegenerationWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            day=state.day,
            instruction=state.instruction,
            regenerated_day=regenerated_day,
        )

    def _day_fallback_node(self, state: DayRegenerationWorkflowState) -> DayRegenerationWorkflowState:
        if state.regenerated_day:
            return state
        return DayRegenerationWorkflowState(
            saved_trip_plan=state.saved_trip_plan,
            day=state.day,
            instruction=state.instruction,
            regenerated_day=build_mock_regenerated_trip_day(
                state.saved_trip_plan,
                state.day,
                state.instruction,
            ),
            fallback_used=True,
        )

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


def _chat_node_events(state: ChatWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    llm_event = (
        _node_event("chat_llm", "SKIPPED", "llm_disabled_or_empty_response")
        if state.fallback_used
        else _node_event("chat_llm", "SUCCEEDED", "chat_reply_generated")
    )
    fallback_event = (
        _node_event("chat_fallback", "FALLBACK", "rule_based_reply")
        if state.fallback_used
        else _node_event("chat_fallback", "SKIPPED", "llm_response_available")
    )
    return (llm_event, fallback_event)


def _trip_node_events(state: TripPlanningWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    draft_event = (
        _node_event("trip_draft", "SKIPPED", "llm_disabled_or_invalid_response")
        if state.draft_plan is None
        else _node_event("trip_draft", "SUCCEEDED", "draft_plan_generated")
    )
    enrichment_event = (
        _node_event("trip_enrichment", "SUCCEEDED", "travel_tools_applied")
        if state.final_plan is not None and state.draft_plan is not None
        else _node_event("trip_enrichment", "SKIPPED", "no_draft_plan_to_enrich")
    )
    validation_event = (
        _node_event("trip_validation", "FALLBACK", "mock_trip_plan_generated")
        if state.fallback_used
        else _node_event("trip_validation", "SUCCEEDED", "plan_has_days")
    )
    return (draft_event, enrichment_event, validation_event)


def _day_node_events(state: DayRegenerationWorkflowState) -> tuple[TravelAgentNodeEvent, ...]:
    generation_event = (
        _node_event("day_regeneration", "SKIPPED", "llm_disabled_or_invalid_response")
        if state.fallback_used
        else _node_event("day_regeneration", "SUCCEEDED", "day_json_generated")
    )
    fallback_event = (
        _node_event("day_fallback", "FALLBACK", "mock_day_generated")
        if state.fallback_used
        else _node_event("day_fallback", "SKIPPED", "llm_day_available")
    )
    return (generation_event, fallback_event)


def _node_event(node_name: str, status: str, detail: str) -> TravelAgentNodeEvent:
    return TravelAgentNodeEvent(node_name=node_name, status=status, detail=detail)

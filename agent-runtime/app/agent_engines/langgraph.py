from dataclasses import dataclass

from app.llm import LLMClient
from app.planner import build_mock_regenerated_trip_day, build_mock_trip_plan, enrich_trip_plan_response
from app.schemas import AgentMode, ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider


@dataclass
class ChatWorkflowState:
    request: ChatRequest
    messages: list[ChatMessage]
    response: str | None = None


@dataclass
class TripPlanningWorkflowState:
    request: TripPlanRequest
    draft_plan: TripPlanResponse | None = None
    final_plan: TripPlanResponse | None = None


@dataclass
class DayRegenerationWorkflowState:
    saved_trip_plan: SavedTripPlan
    day: int
    instruction: str
    regenerated_day: TripDay | None = None


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

    @property
    def llm_enabled(self) -> bool:
        return self._llm_client.enabled

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        state = ChatWorkflowState(request=request, messages=messages)
        state = self._chat_llm_node(state)
        state = self._chat_fallback_node(state)
        return state.response or _build_rule_based_reply(request)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        state = TripPlanningWorkflowState(request=request)
        state = self._trip_draft_node(state)
        state = self._trip_enrichment_node(state)
        state = self._trip_validation_node(state)
        return state.final_plan or build_mock_trip_plan(request, self._travel_tools)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        state = DayRegenerationWorkflowState(
            saved_trip_plan=saved_trip_plan,
            day=day,
            instruction=instruction,
        )
        state = self._day_regeneration_node(state)
        state = self._day_fallback_node(state)
        return state.regenerated_day or build_mock_regenerated_trip_day(saved_trip_plan, day, instruction)

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
        )

    def _trip_validation_node(self, state: TripPlanningWorkflowState) -> TripPlanningWorkflowState:
        if not state.final_plan or not state.final_plan.days:
            fallback_plan = build_mock_trip_plan(state.request, self._travel_tools)
            return TripPlanningWorkflowState(
                request=state.request,
                draft_plan=state.draft_plan,
                final_plan=fallback_plan,
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

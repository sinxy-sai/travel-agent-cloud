from app.agent_engines import create_travel_agent_engine
from app.agent_engines.types import (
    TravelAgentEngine,
    TravelAgentEngineCapabilities,
    TravelAgentRunSummary,
    TravelAgentRunTrace,
    TravelAgentToolCallSummary,
)
from app.schemas import ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider


class TravelAgentService:
    def __init__(self, settings: Settings, travel_tools: TravelToolProvider) -> None:
        self._engine = create_travel_agent_engine(settings, travel_tools)

    @property
    def engine(self) -> TravelAgentEngine:
        return self._engine

    @property
    def engine_name(self) -> str:
        return self._engine.name

    @property
    def engine_capabilities(self) -> TravelAgentEngineCapabilities:
        return self._engine.capabilities

    @property
    def last_run_trace(self) -> TravelAgentRunTrace | None:
        return self._engine.last_run_trace

    @property
    def recent_run_traces(self) -> tuple[TravelAgentRunTrace, ...]:
        return self._engine.recent_run_traces

    @property
    def run_summary(self) -> TravelAgentRunSummary:
        return TravelAgentRunSummary.from_traces(self._engine.recent_run_traces)

    @property
    def tool_call_summary(self) -> TravelAgentToolCallSummary:
        return TravelAgentToolCallSummary.from_traces(self._engine.recent_run_traces)

    @property
    def llm_enabled(self) -> bool:
        return self._engine.llm_enabled

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        return self._engine.generate_chat_reply(request, messages)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        return self._engine.generate_trip_plan(request)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        return self._engine.regenerate_trip_day(saved_trip_plan, day, instruction)

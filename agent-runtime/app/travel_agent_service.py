from app.agent_engines import create_travel_agent_engine
from app.agent_engines.types import (
    TravelAgentEngine,
    TravelAgentEngineCapabilities,
    TravelAgentQualitySummary,
    TravelAgentRunSummary,
    TravelAgentRunTrace,
    TravelAgentToolCallSummary,
)
from app.schemas import (
    ChatMessage,
    ChatRequest,
    KnowledgeRecordCreateRequest,
    SavedTripPlan,
    TripDay,
    TripPlanRequest,
    TripPlanResponse,
)
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
    def quality_summary(self) -> TravelAgentQualitySummary:
        return TravelAgentQualitySummary.from_traces(self._engine.recent_run_traces)

    @property
    def tool_call_summary(self) -> TravelAgentToolCallSummary:
        return TravelAgentToolCallSummary.from_traces(self._engine.recent_run_traces)

    @property
    def llm_enabled(self) -> bool:
        return self._engine.llm_enabled

    @property
    def knowledge_backend(self) -> str:
        return str(getattr(self._engine, "knowledge_backend", "disabled"))

    def list_knowledge_records(self, destination: str | None = None, limit: int = 20) -> tuple[dict[str, object], ...]:
        return self._engine.list_knowledge_records(destination, limit)

    def seed_destination_knowledge(self, destination: str) -> int:
        return self._engine.seed_destination_knowledge(destination)

    def create_knowledge_record(self, request: KnowledgeRecordCreateRequest) -> dict[str, object]:
        return self._engine.create_knowledge_record(request)

    def delete_knowledge_record(self, record_id: str) -> bool:
        return self._engine.delete_knowledge_record(record_id)

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        return self._engine.generate_chat_reply(request, messages)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        return self._engine.generate_trip_plan(request)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        return self._engine.regenerate_trip_day(saved_trip_plan, day, instruction)

    def revise_trip_plan(self, saved_trip_plan: SavedTripPlan, instruction: str) -> TripPlanResponse:
        return self._engine.revise_trip_plan(saved_trip_plan, instruction)

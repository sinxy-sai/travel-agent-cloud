from app.agent_engines import create_travel_agent_engine
from app.agent_engines.types import TravelAgentEngine
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
    def llm_enabled(self) -> bool:
        return self._engine.llm_enabled

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        return self._engine.generate_chat_reply(request, messages)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        return self._engine.generate_trip_plan(request)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        return self._engine.regenerate_trip_day(saved_trip_plan, day, instruction)

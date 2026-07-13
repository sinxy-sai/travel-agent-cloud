from app.agent_engines.basic import BasicTravelAgentEngine
from app.schemas import ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider


class LangGraphTravelAgentEngine:
    """Placeholder for the future LangGraph workflow engine.

    The public engine contract is stable now, but the LangGraph dependency and
    graph nodes should be introduced only after the chat/trip contracts settle.
    Until then, this engine keeps the deployment path valid and delegates to the
    current basic implementation.
    """

    name = "langgraph:basic-fallback"

    def __init__(self, settings: Settings, travel_tools: TravelToolProvider) -> None:
        self._fallback = BasicTravelAgentEngine(settings, travel_tools, name=self.name)

    @property
    def llm_enabled(self) -> bool:
        return self._fallback.llm_enabled

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        return self._fallback.generate_chat_reply(request, messages)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        return self._fallback.generate_trip_plan(request)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        return self._fallback.regenerate_trip_day(saved_trip_plan, day, instruction)

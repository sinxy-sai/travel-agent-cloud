from app.llm import LLMClient
from app.planner import build_mock_regenerated_trip_day, build_mock_trip_plan, enrich_trip_plan_response
from app.schemas import AgentMode, ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse
from app.settings import Settings
from app.travel_tools import TravelToolProvider
from app.agent_engines.types import TravelAgentEngineCapabilities


class BasicTravelAgentEngine:
    def __init__(self, settings: Settings, travel_tools: TravelToolProvider, name: str = "basic") -> None:
        self.name = name
        self._llm_client = LLMClient(settings)
        self._travel_tools = travel_tools

    @property
    def llm_enabled(self) -> bool:
        return self._llm_client.enabled

    @property
    def capabilities(self) -> TravelAgentEngineCapabilities:
        return TravelAgentEngineCapabilities(
            supports_chat=True,
            supports_trip_planning=True,
            supports_day_regeneration=True,
            workflow_nodes=("llm_call", "tool_enrichment", "mock_fallback"),
            dependency_mode="builtin",
        )

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        return self._llm_client.generate_chat_reply(messages, request.mode) or _build_rule_based_reply(request)

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        llm_response = self._llm_client.generate_trip_plan(request)
        if llm_response:
            return enrich_trip_plan_response(llm_response, request, self._travel_tools)
        return build_mock_trip_plan(request, self._travel_tools)

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        return self._llm_client.regenerate_trip_day(
            saved_trip_plan,
            day,
            instruction,
        ) or build_mock_regenerated_trip_day(saved_trip_plan, day, instruction)


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

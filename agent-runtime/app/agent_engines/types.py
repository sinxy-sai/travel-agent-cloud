from dataclasses import dataclass
from typing import Protocol

from app.schemas import ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse


@dataclass(frozen=True)
class TravelAgentEngineCapabilities:
    supports_chat: bool
    supports_trip_planning: bool
    supports_day_regeneration: bool
    workflow_nodes: tuple[str, ...]
    dependency_mode: str

    def to_dict(self) -> dict[str, bool | str | list[str]]:
        return {
            "supportsChat": self.supports_chat,
            "supportsTripPlanning": self.supports_trip_planning,
            "supportsDayRegeneration": self.supports_day_regeneration,
            "workflowNodes": list(self.workflow_nodes),
            "dependencyMode": self.dependency_mode,
        }


class TravelAgentEngine(Protocol):
    name: str

    @property
    def llm_enabled(self) -> bool:
        ...

    @property
    def capabilities(self) -> TravelAgentEngineCapabilities:
        ...

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        ...

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        ...

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        ...

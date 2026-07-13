from typing import Protocol

from app.schemas import ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse


class TravelAgentEngine(Protocol):
    name: str

    @property
    def llm_enabled(self) -> bool:
        ...

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        ...

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        ...

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        ...

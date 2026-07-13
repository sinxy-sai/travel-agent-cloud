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


@dataclass(frozen=True)
class TravelAgentRunTrace:
    run_id: str
    operation: str
    engine_name: str
    started_at: str
    duration_ms: int
    workflow_nodes: tuple[str, ...]
    completed_nodes: tuple[str, ...]
    fallback_used: bool
    llm_enabled: bool

    def to_dict(self) -> dict[str, bool | int | str | list[str]]:
        return {
            "runId": self.run_id,
            "operation": self.operation,
            "engineName": self.engine_name,
            "startedAt": self.started_at,
            "durationMs": self.duration_ms,
            "workflowNodes": list(self.workflow_nodes),
            "completedNodes": list(self.completed_nodes),
            "fallbackUsed": self.fallback_used,
            "llmEnabled": self.llm_enabled,
        }


class TravelAgentEngine(Protocol):
    name: str

    @property
    def llm_enabled(self) -> bool:
        ...

    @property
    def capabilities(self) -> TravelAgentEngineCapabilities:
        ...

    @property
    def last_run_trace(self) -> TravelAgentRunTrace | None:
        ...

    @property
    def recent_run_traces(self) -> tuple[TravelAgentRunTrace, ...]:
        ...

    def generate_chat_reply(self, request: ChatRequest, messages: list[ChatMessage]) -> str:
        ...

    def generate_trip_plan(self, request: TripPlanRequest) -> TripPlanResponse:
        ...

    def regenerate_trip_day(self, saved_trip_plan: SavedTripPlan, day: int, instruction: str) -> TripDay:
        ...

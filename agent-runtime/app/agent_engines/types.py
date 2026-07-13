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
class TravelAgentNodeEvent:
    node_name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "nodeName": self.node_name,
            "status": self.status,
            "detail": self.detail,
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
    node_events: tuple[TravelAgentNodeEvent, ...] = ()

    def to_dict(self) -> dict[str, bool | int | str | list[str] | list[dict[str, str]]]:
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
            "nodeEvents": [event.to_dict() for event in self.node_events],
        }


@dataclass(frozen=True)
class TravelAgentRunSummary:
    window_size: int
    total_runs: int
    fallback_runs: int
    average_duration_ms: int
    operation_counts: dict[str, int]

    @classmethod
    def from_traces(cls, traces: tuple[TravelAgentRunTrace, ...]) -> "TravelAgentRunSummary":
        total_runs = len(traces)
        fallback_runs = sum(1 for trace in traces if trace.fallback_used)
        total_duration_ms = sum(trace.duration_ms for trace in traces)
        operation_counts: dict[str, int] = {}
        for trace in traces:
            operation_counts[trace.operation] = operation_counts.get(trace.operation, 0) + 1

        return cls(
            window_size=total_runs,
            total_runs=total_runs,
            fallback_runs=fallback_runs,
            average_duration_ms=round(total_duration_ms / total_runs) if total_runs else 0,
            operation_counts=operation_counts,
        )

    def to_dict(self) -> dict[str, int | dict[str, int]]:
        return {
            "windowSize": self.window_size,
            "totalRuns": self.total_runs,
            "fallbackRuns": self.fallback_runs,
            "averageDurationMs": self.average_duration_ms,
            "operationCounts": self.operation_counts,
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

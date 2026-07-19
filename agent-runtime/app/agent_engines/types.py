from dataclasses import dataclass
from typing import Protocol

from app.schemas import ChatMessage, ChatRequest, SavedTripPlan, TripDay, TripPlanRequest, TripPlanResponse


@dataclass(frozen=True)
class TravelAgentEngineCapabilities:
    supports_chat: bool
    supports_trip_planning: bool
    supports_day_regeneration: bool
    supports_trip_revision: bool
    workflow_nodes: tuple[str, ...]
    dependency_mode: str

    def to_dict(self) -> dict[str, bool | str | list[str]]:
        return {
            "supportsChat": self.supports_chat,
            "supportsTripPlanning": self.supports_trip_planning,
            "supportsDayRegeneration": self.supports_day_regeneration,
            "supportsTripRevision": self.supports_trip_revision,
            "workflowNodes": list(self.workflow_nodes),
            "dependencyMode": self.dependency_mode,
        }


@dataclass(frozen=True)
class TravelAgentNodeEvent:
    node_name: str
    status: str
    detail: str = ""
    score: int | None = None
    grade: str | None = None

    def to_dict(self) -> dict[str, str | int]:
        payload: dict[str, str | int] = {
            "nodeName": self.node_name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.score is not None:
            payload["score"] = self.score
        if self.grade is not None:
            payload["grade"] = self.grade
        return payload


@dataclass(frozen=True)
class TravelAgentToolCall:
    tool_name: str
    status: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "toolName": self.tool_name,
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
    tool_calls: tuple[TravelAgentToolCall, ...] = ()

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
            "toolCalls": [tool_call.to_dict() for tool_call in self.tool_calls],
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


@dataclass(frozen=True)
class TravelAgentQualitySummary:
    window_size: int
    scored_runs: int
    average_score: int
    latest_score: int | None
    latest_grade: str
    grade_counts: dict[str, int]

    @classmethod
    def from_traces(cls, traces: tuple[TravelAgentRunTrace, ...]) -> "TravelAgentQualitySummary":
        scores: list[int] = []
        grade_counts: dict[str, int] = {}
        latest_score: int | None = None
        latest_grade = ""

        for trace in traces:
            scored_event = next((event for event in trace.node_events if event.score is not None), None)
            if scored_event is None:
                continue
            score = int(scored_event.score)
            grade = scored_event.grade or "unknown"
            if latest_score is None:
                latest_score = score
                latest_grade = grade
            scores.append(score)
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

        return cls(
            window_size=len(traces),
            scored_runs=len(scores),
            average_score=round(sum(scores) / len(scores)) if scores else 0,
            latest_score=latest_score,
            latest_grade=latest_grade,
            grade_counts=grade_counts,
        )

    def to_dict(self) -> dict[str, int | str | None | dict[str, int]]:
        return {
            "windowSize": self.window_size,
            "scoredRuns": self.scored_runs,
            "averageScore": self.average_score,
            "latestScore": self.latest_score,
            "latestGrade": self.latest_grade,
            "gradeCounts": self.grade_counts,
        }


@dataclass(frozen=True)
class TravelAgentToolCallSummary:
    window_size: int
    total_tool_calls: int
    failed_tool_calls: int
    tool_counts: dict[str, int]
    status_counts: dict[str, int]

    @classmethod
    def from_traces(cls, traces: tuple[TravelAgentRunTrace, ...]) -> "TravelAgentToolCallSummary":
        tool_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_tool_calls = 0
        failed_tool_calls = 0
        for trace in traces:
            for tool_call in trace.tool_calls:
                total_tool_calls += 1
                tool_counts[tool_call.tool_name] = tool_counts.get(tool_call.tool_name, 0) + 1
                status_counts[tool_call.status] = status_counts.get(tool_call.status, 0) + 1
                if tool_call.status == "FAILED":
                    failed_tool_calls += 1

        return cls(
            window_size=len(traces),
            total_tool_calls=total_tool_calls,
            failed_tool_calls=failed_tool_calls,
            tool_counts=tool_counts,
            status_counts=status_counts,
        )

    def to_dict(self) -> dict[str, int | dict[str, int]]:
        return {
            "windowSize": self.window_size,
            "totalToolCalls": self.total_tool_calls,
            "failedToolCalls": self.failed_tool_calls,
            "toolCounts": self.tool_counts,
            "statusCounts": self.status_counts,
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

    def revise_trip_plan(self, saved_trip_plan: SavedTripPlan, instruction: str) -> TripPlanResponse:
        ...

    @property
    def knowledge_backend(self) -> str:
        ...

    def list_knowledge_records(self, destination: str | None = None, limit: int = 20) -> tuple[dict[str, object], ...]:
        ...

    def seed_destination_knowledge(self, destination: str) -> int:
        ...

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from app.data_sources import summarize_trip_plan_data_sources
from app.metrics import add_metrics
from app.observability import RequestLoggingMiddleware, configure_logging
from app.progress import trip_plan_progress
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    KnowledgeRecordCreateRequest,
    MessageRole,
    RuntimeTripDayRegenerateRequest,
    RuntimeTripPlanReviseRequest,
    TripPlanRequest,
    TripPlanResponse,
)
from app.security import InternalServiceAuthMiddleware, SecurityHeadersMiddleware
from app.settings import get_settings
from app.tracing import add_tracing
from app.travel_agent_service import TravelAgentService
from app.travel_tools import create_travel_tool_provider
from app.users import DEFAULT_USER_ID, get_user_id

settings = get_settings()
configure_logging(settings)
travel_tool_provider = create_travel_tool_provider(settings)
travel_agent_service = TravelAgentService(settings, travel_tool_provider)
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(InternalServiceAuthMiddleware, token=settings.internal_service_token)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
add_metrics(app, service_name="agent-runtime")
add_tracing(app, service_name="agent-runtime")


@app.get("/health")
def health() -> dict[str, str | bool | dict[str, bool | str | list[str]]]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "llmEnabled": travel_agent_service.llm_enabled,
        "agentEngine": travel_agent_service.engine_name,
        "agentEngineCapabilities": travel_agent_service.engine_capabilities.to_dict(),
        "travelToolsProvider": travel_tool_provider.name,
        "ragEnabled": settings.rag_enabled,
        "ragBackend": travel_agent_service.knowledge_backend,
    }


@app.get("/api/v1/agent/status")
def agent_status() -> dict[str, object]:
    last_run_trace = travel_agent_service.last_run_trace
    return {
        "engine": travel_agent_service.engine_name,
        "llmEnabled": travel_agent_service.llm_enabled,
        "capabilities": travel_agent_service.engine_capabilities.to_dict(),
        "lastRunTrace": last_run_trace.to_dict() if last_run_trace else None,
        "recentRunTraces": [trace.to_dict() for trace in travel_agent_service.recent_run_traces],
        "runSummary": travel_agent_service.run_summary.to_dict(),
        "qualitySummary": travel_agent_service.quality_summary.to_dict(),
        "toolCallSummary": travel_agent_service.tool_call_summary.to_dict(),
        "toolCatalog": _travel_tool_catalog(),
        "ragBackend": travel_agent_service.knowledge_backend,
    }


@app.get("/api/v1/agent/tools")
def agent_tools() -> dict[str, object]:
    return _travel_tool_catalog()


@app.get("/api/v1/agent/knowledge")
def agent_knowledge(
    destination: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    records = travel_agent_service.list_knowledge_records(destination, limit)
    return {
        "backend": travel_agent_service.knowledge_backend,
        "count": len(records),
        "records": list(records),
    }


@app.post("/api/v1/agent/knowledge/seed")
def seed_agent_knowledge(
    destination: str = Query(min_length=1, max_length=120),
    user_id: str = Depends(get_user_id),
) -> dict[str, object]:
    _require_non_anonymous_user(user_id)
    inserted = travel_agent_service.seed_destination_knowledge(destination)
    return {
        "backend": travel_agent_service.knowledge_backend,
        "destination": destination,
        "inserted": inserted,
    }


@app.post("/api/v1/agent/knowledge", status_code=status.HTTP_201_CREATED)
def create_agent_knowledge_record(
    request: KnowledgeRecordCreateRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, object]:
    _require_non_anonymous_user(user_id)
    try:
        record = travel_agent_service.create_knowledge_record(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "KNOWLEDGE_BACKEND_UNAVAILABLE", "message": str(exc)},
        ) from exc
    return {
        "backend": travel_agent_service.knowledge_backend,
        "record": record,
    }


@app.delete("/api/v1/agent/knowledge/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_knowledge_record(
    record_id: str = Path(min_length=1, max_length=120),
    user_id: str = Depends(get_user_id),
) -> None:
    _require_non_anonymous_user(user_id)
    deleted = travel_agent_service.delete_knowledge_record(record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KNOWLEDGE_RECORD_NOT_FOUND", "message": "Knowledge record not found"},
        )


def _require_non_anonymous_user(user_id: str) -> None:
    if not user_id or user_id == DEFAULT_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )


@app.get("/api/v1/agent/diagnostics")
def agent_diagnostics() -> dict[str, object]:
    capabilities = travel_agent_service.engine_capabilities
    run_summary = travel_agent_service.run_summary
    quality_summary = travel_agent_service.quality_summary
    tool_catalog = _travel_tool_catalog()
    checks = _agent_diagnostic_checks(capabilities, run_summary.total_runs, quality_summary, tool_catalog)
    status_counts: dict[str, int] = {}
    for check in checks:
        status_value = str(check["status"])
        status_counts[status_value] = status_counts.get(status_value, 0) + 1

    overall_status = "OK"
    if status_counts.get("FAILED", 0) > 0:
        overall_status = "FAILED"
    elif status_counts.get("DEGRADED", 0) > 0 or status_counts.get("DISABLED", 0) > 0:
        overall_status = "DEGRADED"

    last_run_trace = travel_agent_service.last_run_trace
    return {
        "status": overall_status,
        "engine": travel_agent_service.engine_name,
        "dependencyMode": capabilities.dependency_mode,
        "llmEnabled": travel_agent_service.llm_enabled,
        "toolProvider": travel_tool_provider.name,
        "checks": checks,
        "statusCounts": status_counts,
        "capabilities": capabilities.to_dict(),
        "toolCatalog": tool_catalog,
        "ragBackend": travel_agent_service.knowledge_backend,
        "runSummary": run_summary.to_dict(),
        "qualitySummary": quality_summary.to_dict(),
        "lastRunTrace": last_run_trace.to_dict() if last_run_trace else None,
    }


@app.post("/internal/v1/trip-plan", response_model=TripPlanResponse)
def create_trip_plan(request: TripPlanRequest, user_id: str = Depends(get_user_id)) -> TripPlanResponse:
    return _create_trip_plan_for_user(request)


def _create_trip_plan_for_user(
    request: TripPlanRequest,
    on_stage=None,
) -> TripPlanResponse:
    with trip_plan_progress(on_stage):
        response = travel_agent_service.generate_trip_plan(request)
    if travel_agent_service.last_run_trace and travel_agent_service.last_run_trace.operation == "trip_plan":
        response.data_sources = summarize_trip_plan_data_sources(travel_agent_service.last_run_trace)
    return response


@app.post("/internal/v1/agent/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_id: str = Depends(get_user_id)) -> ChatResponse:
    content = travel_agent_service.generate_chat_reply(request, [])
    return ChatResponse(
        conversation_id=request.conversation_id or str(uuid4()),
        message=ChatMessage(
            id=str(uuid4()),
            role=MessageRole.ASSISTANT,
            content=content,
            created_at=datetime.now(UTC),
        ),
        suggestions=[
            "Generate a structured itinerary",
            "Add weather and transit constraints",
            "Save this plan to my trip list",
        ],
    )

@app.post("/internal/v1/trip-plans/{trip_plan_id}/revise", response_model=TripPlanResponse)
def revise_trip_plan(
    trip_plan_id: str,
    request: RuntimeTripPlanReviseRequest,
    user_id: str = Depends(get_user_id),
) -> TripPlanResponse:
    saved_trip_plan = request.saved_trip_plan
    if request.expected_version != saved_trip_plan.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        )

    revised_plan = travel_agent_service.revise_trip_plan(saved_trip_plan, request.instruction)
    return revised_plan.model_copy(
        update={
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )


@app.post("/internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate", response_model=TripPlanResponse)
def regenerate_trip_plan_day(
    trip_plan_id: str,
    request: RuntimeTripDayRegenerateRequest,
    day: int = Path(ge=1, le=30),
    user_id: str = Depends(get_user_id),
) -> TripPlanResponse:
    saved_trip_plan = request.saved_trip_plan
    if request.expected_version != saved_trip_plan.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        )

    if not any(item.day == day for item in saved_trip_plan.plan.days):
        raise HTTPException(
            status_code=404,
            detail={"code": "TRIP_PLAN_DAY_NOT_FOUND", "message": "Trip plan day not found"},
        )

    regenerated_day = travel_agent_service.regenerate_trip_day(saved_trip_plan, day, request.instruction)
    updated_plan = saved_trip_plan.plan.model_copy(
        update={
            "days": [regenerated_day if item.day == day else item for item in saved_trip_plan.plan.days],
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )
    return updated_plan

def _travel_tool_catalog() -> dict[str, object]:
    tools = [tool.to_dict() for tool in travel_tool_provider.list_tools()]
    return {
        "provider": travel_tool_provider.name,
        "toolCount": len(tools),
        "tools": tools,
    }


def _agent_diagnostic_checks(
    capabilities: object,
    total_runs: int,
    quality_summary: object,
    tool_catalog: dict[str, object],
) -> list[dict[str, str]]:
    workflow_nodes = getattr(capabilities, "workflow_nodes", ())
    scored_runs = int(getattr(quality_summary, "scored_runs", 0))
    latest_grade = str(getattr(quality_summary, "latest_grade", ""))
    latest_score = getattr(quality_summary, "latest_score", None)
    checks = [
        {
            "name": "runtime",
            "status": "OK",
            "detail": "Agent runtime process is reachable.",
        },
        {
            "name": "engine",
            "status": "OK",
            "detail": f"{travel_agent_service.engine_name} is active.",
        },
        {
            "name": "workflow",
            "status": "OK" if workflow_nodes else "FAILED",
            "detail": f"{len(workflow_nodes)} workflow nodes registered.",
        },
        {
            "name": "llm",
            "status": "OK" if travel_agent_service.llm_enabled else "DEGRADED",
            "detail": (
                "LLM provider is configured."
                if travel_agent_service.llm_enabled
                else "LLM is disabled; fallback generation is active."
            ),
        },
        {
            "name": "travel_tools",
            "status": _travel_tools_diagnostic_status(str(tool_catalog["provider"]), int(tool_catalog["toolCount"])),
            "detail": _travel_tools_diagnostic_detail(str(tool_catalog["provider"]), int(tool_catalog["toolCount"])),
        },
        {
            "name": "trace_history",
            "status": "OK" if total_runs > 0 else "DISABLED",
            "detail": (
                f"{total_runs} recent agent runs recorded."
                if total_runs > 0
                else "No agent run has been recorded since startup."
            ),
        },
        {
            "name": "plan_quality",
            "status": _plan_quality_diagnostic_status(scored_runs, latest_grade),
            "detail": _plan_quality_diagnostic_detail(scored_runs, latest_grade, latest_score),
        },
    ]
    return checks


def _plan_quality_diagnostic_status(scored_runs: int, latest_grade: str) -> str:
    if scored_runs <= 0:
        return "DISABLED"
    if latest_grade == "ready":
        return "OK"
    return "DEGRADED"


def _plan_quality_diagnostic_detail(scored_runs: int, latest_grade: str, latest_score: object) -> str:
    if scored_runs <= 0:
        return "No trip plan quality score has been recorded since startup."
    return f"{scored_runs} scored trip plan runs; latest grade {latest_grade or 'unknown'} score {latest_score}."


def _travel_tools_diagnostic_status(provider: str, tool_count: int) -> str:
    if tool_count <= 0:
        return "FAILED"
    if provider == "mock" or provider.startswith("mock:"):
        return "DEGRADED"
    return "OK"


def _travel_tools_diagnostic_detail(provider: str, tool_count: int) -> str:
    if tool_count <= 0:
        return "No travel tools are registered."
    if provider == "mock" or provider.startswith("mock:"):
        return f"{tool_count} mock travel tools are registered; real provider integration is pending."
    return f"{tool_count} travel tools are registered."

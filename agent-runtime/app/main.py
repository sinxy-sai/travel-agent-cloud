import asyncio
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.agent import handle_chat
from app.conversations import (
    ConversationNotFoundError,
    ConversationStore,
    DatabaseConversationStore,
    TripPlanNotFoundError,
    TripPlanVersionConflictError,
)
from app.data_sources import summarize_trip_plan_data_sources
from app.db import maybe_create_session_factory
from app.events import create_event_publisher
from app.observability import RequestLoggingMiddleware, configure_logging
from app.progress import trip_plan_progress
from app.schemas import (
    ChatRequest,
    ChatResponse,
    MessageRole,
    SavedTripPlan,
    TripPlanJob,
    TripPlanReviseRequest,
    TripDayRegenerateRequest,
    TripPlanRequest,
    TripPlanResponse,
    TripPlanUpdateRequest,
)
from app.security import InternalServiceAuthMiddleware, SecurityHeadersMiddleware
from app.settings import get_settings
from app.trip_plan_jobs import TripPlanJobNotFoundError, TripPlanJobStore
from app.travel_agent_service import TravelAgentService
from app.travel_tools import create_travel_tool_provider
from app.users import get_user_id

settings = get_settings()
configure_logging(settings)
session_factory = maybe_create_session_factory(settings)
conversation_store = DatabaseConversationStore(session_factory) if session_factory else ConversationStore()
trip_plan_job_store = TripPlanJobStore()
event_publisher = create_event_publisher(settings)
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


@app.get("/health")
def health() -> dict[str, str | bool | dict[str, bool | str | list[str]]]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "llmEnabled": travel_agent_service.llm_enabled,
        "databaseEnabled": session_factory is not None,
        "messageQueueEnabled": event_publisher.enabled,
        "redisRateLimitEnabled": False,
        "objectStorageEnabled": False,
        "githubOAuthEnabled": False,
        "agentEngine": travel_agent_service.engine_name,
        "agentEngineCapabilities": travel_agent_service.engine_capabilities.to_dict(),
        "travelToolsProvider": travel_tool_provider.name,
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
    }


@app.get("/api/v1/agent/tools")
def agent_tools() -> dict[str, object]:
    return _travel_tool_catalog()


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
        "runSummary": run_summary.to_dict(),
        "qualitySummary": quality_summary.to_dict(),
        "lastRunTrace": last_run_trace.to_dict() if last_run_trace else None,
    }


@app.post("/internal/v1/trip-plan", response_model=TripPlanResponse)
def create_trip_plan(request: TripPlanRequest, user_id: str = Depends(get_user_id)) -> TripPlanResponse:
    return _create_trip_plan_for_user(request, user_id)


@app.post("/internal/v1/trip-plan-jobs", response_model=TripPlanJob, status_code=status.HTTP_202_ACCEPTED)
def create_trip_plan_job(
    request: TripPlanRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
) -> TripPlanJob:
    job = trip_plan_job_store.create(user_id)
    background_tasks.add_task(_run_trip_plan_job, user_id, job.id, request.model_copy(deep=True))
    return job


@app.get("/internal/v1/trip-plan-jobs/{job_id}", response_model=TripPlanJob)
def get_trip_plan_job(job_id: str, user_id: str = Depends(get_user_id)) -> TripPlanJob:
    try:
        return trip_plan_job_store.get(user_id, job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"}) from exc


@app.get("/internal/v1/trip-plan-jobs/{job_id}/events")
def stream_trip_plan_job(job_id: str, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    try:
        trip_plan_job_store.get(user_id, job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"}) from exc
    return StreamingResponse(
        _trip_plan_job_event_stream(user_id, job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _trip_plan_job_event_stream(user_id: str, job_id: str):
    while True:
        try:
            job = trip_plan_job_store.get(user_id, job_id)
        except TripPlanJobNotFoundError:
            yield 'event: error\ndata: {"message":"Trip plan job not found"}\n\n'
            return
        yield f"data: {job.model_dump_json(by_alias=True)}\n\n"
        if job.status in {"SUCCEEDED", "FAILED"}:
            return
        await asyncio.sleep(0.8)


def _run_trip_plan_job(user_id: str, job_id: str, request: TripPlanRequest) -> None:
    try:
        trip_plan_job_store.mark_running(user_id, job_id)
        response = _create_trip_plan_for_user(
            request,
            user_id,
            on_stage=lambda stage_key: trip_plan_job_store.mark_stage_running(user_id, job_id, stage_key),
        )
        trip_plan_job_store.mark_succeeded(user_id, job_id, response)
    except Exception as exc:
        trip_plan_job_store.mark_failed(user_id, job_id, str(exc) or exc.__class__.__name__)


def _create_trip_plan_for_user(
    request: TripPlanRequest,
    user_id: str,
    on_stage=None,
) -> TripPlanResponse:
    with trip_plan_progress(on_stage):
        response = travel_agent_service.generate_trip_plan(request)
    if travel_agent_service.last_run_trace and travel_agent_service.last_run_trace.operation == "trip_plan":
        response.data_sources = summarize_trip_plan_data_sources(travel_agent_service.last_run_trace)
    if on_stage:
        on_stage("saving")
    try:
        conversation = conversation_store.get_or_create(
            user_id=user_id,
            conversation_id=request.conversation_id,
            mode="TRIP_PLANNING",
            title=response.title,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc
    conversation_store.append_message(
        conversation,
        MessageRole.USER,
        f"Plan {request.days} days in {request.destination}, budget={request.budget}, interests={request.interests}",
    )
    conversation_store.append_message(conversation, MessageRole.ASSISTANT, response.summary)
    saved_trip_plan = _save_generated_trip_plan(user_id, conversation.id, request, response)
    response.saved_trip_plan_id = saved_trip_plan.id
    response.conversation_id = conversation.id
    event_publisher.publish(
        "trip.plan.created",
        user_id,
        {
            "tripPlanId": saved_trip_plan.id,
            "conversationId": conversation.id,
            "destination": request.destination,
            "days": request.days,
        },
    )
    return response


def _save_generated_trip_plan(
    user_id: str,
    conversation_id: str,
    request: TripPlanRequest,
    response: TripPlanResponse,
) -> SavedTripPlan:
    if settings.travel_trip_url.strip():
        try:
            with httpx.Client(timeout=settings.travel_trip_timeout_seconds) as client:
                trip_response = client.post(
                    f"{settings.travel_trip_url.rstrip('/')}/internal/v1/trip-plans",
                    headers=_internal_service_headers(user_id=user_id),
                    json={
                        "request": request.model_dump(mode="json", by_alias=True),
                        "plan": response.model_dump(mode="json", by_alias=True),
                        "conversationId": conversation_id,
                    },
                )
                trip_response.raise_for_status()
            return SavedTripPlan.model_validate(trip_response.json())
        except (httpx.HTTPError, ValueError):
            pass

    conversation = conversation_store.get(user_id, conversation_id)
    return conversation_store.save_trip_plan(user_id, conversation, request, response)


def _update_trip_plan_content(
    user_id: str,
    trip_plan_id: str,
    request: TripPlanUpdateRequest,
    *,
    source: str,
) -> SavedTripPlan:
    if settings.travel_trip_url.strip():
        try:
            with httpx.Client(timeout=settings.travel_trip_timeout_seconds) as client:
                trip_response = client.patch(
                    f"{settings.travel_trip_url.rstrip('/')}/internal/v1/trip-plans/{trip_plan_id}",
                    headers=_internal_service_headers(user_id=user_id),
                    json={
                        **request.model_dump(mode="json", by_alias=True, exclude_none=True),
                        "source": source,
                    },
                )
            if trip_response.status_code == status.HTTP_404_NOT_FOUND:
                raise TripPlanNotFoundError(trip_plan_id)
            if trip_response.status_code == status.HTTP_409_CONFLICT:
                raise TripPlanVersionConflictError(trip_plan_id)
            trip_response.raise_for_status()
            return SavedTripPlan.model_validate(trip_response.json())
        except (TripPlanNotFoundError, TripPlanVersionConflictError):
            raise
        except (httpx.HTTPError, ValueError):
            pass

    return conversation_store.update_trip_plan(user_id, trip_plan_id, request, source=source)


def _internal_service_headers(*, user_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"X-Request-ID": str(uuid4())}
    if user_id:
        headers["X-User-Id"] = user_id
    if settings.internal_service_token.strip():
        headers["X-Travel-Internal-Token"] = settings.internal_service_token.strip()
    return headers


@app.post("/internal/v1/agent/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user_id: str = Depends(get_user_id)) -> ChatResponse:
    try:
        return handle_chat(user_id, request, conversation_store, travel_agent_service)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"}) from exc

@app.post("/internal/v1/trip-plans/{trip_plan_id}/revise", response_model=SavedTripPlan)
def revise_trip_plan(
    trip_plan_id: str,
    request: TripPlanReviseRequest,
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        saved_trip_plan = conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
    if request.expected_version != saved_trip_plan.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        )

    revised_plan = travel_agent_service.revise_trip_plan(saved_trip_plan, request.instruction)
    revised_plan = revised_plan.model_copy(
        update={
            "saved_trip_plan_id": saved_trip_plan.id,
            "conversation_id": saved_trip_plan.conversation_id,
        }
    )

    try:
        trip_plan = _update_trip_plan_content(
            user_id,
            trip_plan_id,
            TripPlanUpdateRequest(plan=revised_plan, expected_version=request.expected_version),
            source="agent_revision",
        )
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "TRIP_PLAN_REVISION_INVALID", "message": "Revised trip plan was invalid"},
        ) from exc

    if trip_plan.conversation_id:
        try:
            conversation = conversation_store.get(user_id, trip_plan.conversation_id)
            conversation_store.append_message(conversation, MessageRole.USER, f"Revise itinerary: {request.instruction}")
            conversation_store.append_message(
                conversation,
                MessageRole.ASSISTANT,
                f"Revised itinerary: {trip_plan.plan.summary}",
            )
        except ConversationNotFoundError:
            pass

    event_publisher.publish(
        "trip.plan.revised",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "version": trip_plan.version,
        },
    )
    return trip_plan


@app.post("/internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate", response_model=SavedTripPlan)
def regenerate_trip_plan_day(
    trip_plan_id: str,
    request: TripDayRegenerateRequest,
    day: int = Path(ge=1, le=30),
    user_id: str = Depends(get_user_id),
) -> SavedTripPlan:
    try:
        saved_trip_plan = conversation_store.get_trip_plan(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"}) from exc
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

    try:
        trip_plan = _update_trip_plan_content(
            user_id,
            trip_plan_id,
            TripPlanUpdateRequest(plan=updated_plan, expected_version=request.expected_version),
            source="day_regeneration",
        )
    except TripPlanVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRIP_PLAN_VERSION_CONFLICT",
                "message": "Trip plan was updated elsewhere; reload it before saving",
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "TRIP_DAY_REGENERATION_INVALID", "message": "Regenerated trip day was invalid"},
        ) from exc

    if trip_plan.conversation_id:
        try:
            conversation = conversation_store.get(user_id, trip_plan.conversation_id)
            conversation_store.append_message(conversation, MessageRole.USER, f"Regenerate day {day}: {request.instruction}")
            conversation_store.append_message(
                conversation,
                MessageRole.ASSISTANT,
                f"Updated day {day}: {regenerated_day.theme}",
            )
        except ConversationNotFoundError:
            pass

    event_publisher.publish(
        "trip.plan.day.regenerated",
        user_id,
        {
            "tripPlanId": trip_plan_id,
            "day": day,
            "version": trip_plan.version,
        },
    )
    return trip_plan

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

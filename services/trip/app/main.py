import os
import asyncio
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.internal_auth import (
    InternalServiceAuthMiddleware,
    RequestContextMiddleware,
    internal_service_headers,
    internal_service_token,
)
from travel_common.metrics import add_metrics
from travel_common.proxy import check_upstream

from app.db import create_session_factory
from app.exporter import saved_trip_plan_to_markdown
from app.schemas import (
    SavedTripPlan,
    TripDayRegenerateRequest,
    TripPlanCreateRequest,
    TripPlanInternalUpdateRequest,
    TripPlanJob,
    TripPlanListResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripPlanReviseRequest,
    TripPlanRestoreRequest,
    TripPlanUpdateRequest,
    TripPlanVersionListResponse,
)
from app.jobs import TripPlanJobNotFoundError, TripPlanJobStore
from app.store import (
    TripPlanNotFoundError,
    TripPlanStore,
    TripPlanVersionConflictError,
    TripPlanVersionNotFoundError,
)
from app.users import current_user_id


APP_NAME = "Travel Trip Service"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("TRIP_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = allowed_origins_from_env()
INTERNAL_SERVICE_TOKEN = internal_service_token()
INTERNAL_SERVICE_HEADERS = internal_service_headers(INTERNAL_SERVICE_TOKEN)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
trip_plan_store = TripPlanStore(session_factory) if session_factory else None
trip_plan_job_store = TripPlanJobStore()

app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(
    InternalServiceAuthMiddleware,
    token=INTERNAL_SERVICE_TOKEN,
    protected_prefixes=("/api/", "/internal/"),
)
app.add_middleware(RequestContextMiddleware)
add_cors(app, allowed_origins=ALLOWED_ORIGINS)
add_metrics(app, service_name="travel-trip")


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await _check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] and trip_plan_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "trip-api-service",
        "databaseEnabled": trip_plan_store is not None,
        "upstreams": {"agentRuntime": upstream},
    }


@app.post("/api/v1/trip-plan", response_model=TripPlanResponse)
async def create_trip_plan(payload: TripPlanRequest, request: Request) -> TripPlanResponse:
    user_id = _required_user_id(request)
    _require_trip_store()
    runtime_plan = TripPlanResponse.model_validate(
        await _runtime_json(
            request,
            "/internal/v1/trip-plan",
            payload.model_dump(mode="json", by_alias=True),
        )
    )
    saved_trip_plan = trip_plan_store.create(  # type: ignore[union-attr]
        user_id,
        TripPlanCreateRequest(
            request=payload,
            plan=runtime_plan,
            conversation_id=payload.conversation_id,
        ),
    )
    return saved_trip_plan.plan


@app.post("/api/v1/trip-plan-jobs", response_model=TripPlanJob, status_code=status.HTTP_202_ACCEPTED)
async def create_trip_plan_job(
    payload: TripPlanRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TripPlanJob:
    user_id = _required_user_id(request)
    _require_trip_store()
    job = trip_plan_job_store.create(user_id)
    background_tasks.add_task(_run_trip_plan_job, user_id, job.id, payload.model_copy(deep=True), _request_id(request))
    return job


@app.get("/api/v1/trip-plan-jobs/{job_id}", response_model=TripPlanJob)
async def get_trip_plan_job(job_id: str, request: Request) -> TripPlanJob:
    try:
        return trip_plan_job_store.get(_required_user_id(request), job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"},
        ) from exc


@app.get("/api/v1/trip-plan-jobs/{job_id}/events")
async def stream_trip_plan_job(job_id: str, request: Request) -> StreamingResponse:
    user_id = _required_user_id(request)
    try:
        trip_plan_job_store.get(user_id, job_id)
    except TripPlanJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_PLAN_JOB_NOT_FOUND", "message": "Trip plan job not found"},
        ) from exc
    return StreamingResponse(
        _trip_plan_job_event_stream(user_id, job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/internal/v1/trip-plans", response_model=SavedTripPlan)
async def create_internal_trip_plan(payload: TripPlanCreateRequest, request: Request) -> SavedTripPlan:
    if not trip_plan_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "TRIP_STORE_UNAVAILABLE", "message": "Trip store is not configured"},
        )
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "USER_ID_REQUIRED", "message": "X-User-Id header is required"},
        )
    return trip_plan_store.create(user_id, payload)


@app.patch("/internal/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
async def update_internal_trip_plan(
    trip_plan_id: str,
    payload: TripPlanInternalUpdateRequest,
    request: Request,
) -> SavedTripPlan:
    if not trip_plan_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "TRIP_STORE_UNAVAILABLE", "message": "Trip store is not configured"},
        )
    user_id = request.headers.get("X-User-Id", "").strip()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "USER_ID_REQUIRED", "message": "X-User-Id header is required"},
        )
    try:
        return trip_plan_store.update(user_id, trip_plan_id, payload, source=payload.source)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.api_route("/api/v1/trip-plans", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def trip_plans_root(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    favorite_only: bool = Query(default=False, alias="favoriteOnly"),
    query: str = Query(default="", max_length=120),
) -> Any:
    if request.method == "GET":
        return _require_trip_store().list(_required_user_id(request), page, page_size, favorite_only, query)
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail={"code": "METHOD_NOT_ALLOWED", "message": "Use a supported trip plan endpoint"},
    )


@app.get("/api/v1/trip-plans/{trip_plan_id}/versions", response_model=TripPlanVersionListResponse)
async def list_trip_plan_versions(
    trip_plan_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> Any:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        return store.list_versions(user_id, trip_plan_id, page, page_size)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc


@app.post("/api/v1/trip-plans/{trip_plan_id}/versions/{version_id}/restore", response_model=SavedTripPlan)
async def restore_trip_plan_version(
    trip_plan_id: str,
    version_id: str,
    payload: TripPlanRestoreRequest,
    request: Request,
) -> Any:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        return store.restore_version(user_id, trip_plan_id, version_id, payload.expected_version)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    except TripPlanVersionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_PLAN_VERSION_NOT_FOUND", "message": "Trip plan version not found"},
        ) from exc
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.get("/api/v1/trip-plans/{trip_plan_id}/export", response_class=PlainTextResponse)
async def export_trip_plan(trip_plan_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        saved_trip_plan = store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    return PlainTextResponse(
        content=saved_trip_plan_to_markdown(saved_trip_plan),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_for_download(saved_trip_plan.title)},
    )


@app.post("/api/v1/trip-plans/{trip_plan_id}/revise", response_model=SavedTripPlan)
async def revise_trip_plan(trip_plan_id: str, payload: TripPlanReviseRequest, request: Request) -> SavedTripPlan:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        saved_trip_plan = store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    _assert_expected_version(saved_trip_plan, payload.expected_version)
    revised_plan = TripPlanResponse.model_validate(
        await _runtime_json(
            request,
            f"/internal/v1/trip-plans/{trip_plan_id}/revise",
            {
                "savedTripPlan": saved_trip_plan.model_dump(mode="json", by_alias=True),
                "instruction": payload.instruction,
                "expectedVersion": payload.expected_version,
            },
        )
    )
    try:
        return store.update(
            user_id,
            trip_plan_id,
            TripPlanInternalUpdateRequest(
                plan=revised_plan,
                expected_version=payload.expected_version,
                source="agent_revision",
            ),
            source="agent_revision",
        )
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.post("/api/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate", response_model=SavedTripPlan)
async def regenerate_trip_plan_day(
    trip_plan_id: str,
    payload: TripDayRegenerateRequest,
    request: Request,
    day: int = Path(ge=1, le=30),
) -> SavedTripPlan:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        saved_trip_plan = store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    _assert_expected_version(saved_trip_plan, payload.expected_version)
    if not any(item.day == day for item in saved_trip_plan.plan.days):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_PLAN_DAY_NOT_FOUND", "message": "Trip plan day not found"},
        )
    updated_plan = TripPlanResponse.model_validate(
        await _runtime_json(
            request,
            f"/internal/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate",
            {
                "savedTripPlan": saved_trip_plan.model_dump(mode="json", by_alias=True),
                "instruction": payload.instruction,
                "expectedVersion": payload.expected_version,
            },
        )
    )
    try:
        return store.update(
            user_id,
            trip_plan_id,
            TripPlanInternalUpdateRequest(
                plan=updated_plan,
                expected_version=payload.expected_version,
                source="day_regeneration",
            ),
            source="day_regeneration",
        )
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.get("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
async def get_trip_plan(trip_plan_id: str, request: Request) -> Any:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        return store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc


@app.patch("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
async def update_trip_plan(
    trip_plan_id: str,
    payload: TripPlanUpdateRequest,
    request: Request,
) -> Any:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        return store.update(user_id, trip_plan_id, payload)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.delete("/api/v1/trip-plans/{trip_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip_plan(trip_plan_id: str, request: Request) -> Response:
    user_id = _required_user_id(request)
    store = _require_trip_store()
    try:
        store.delete(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _check_upstream(url: str) -> dict[str, Any]:
    return await check_upstream(url)


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


def _run_trip_plan_job(user_id: str, job_id: str, payload: TripPlanRequest, request_id: str | None) -> None:
    try:
        store = _require_trip_store()
        trip_plan_job_store.mark_running(user_id, job_id)
        runtime_plan = TripPlanResponse.model_validate(
            _runtime_json_sync(
                "/internal/v1/trip-plan",
                payload.model_dump(mode="json", by_alias=True),
                user_id=user_id,
                request_id=request_id,
            )
        )
        trip_plan_job_store.mark_saving(user_id, job_id)
        saved_trip_plan = store.create(
            user_id,
            TripPlanCreateRequest(
                request=payload,
                plan=runtime_plan,
                conversation_id=payload.conversation_id,
            ),
        )
        trip_plan_job_store.mark_succeeded(user_id, job_id, saved_trip_plan.plan)
    except Exception as exc:
        trip_plan_job_store.mark_failed(user_id, job_id, str(exc) or exc.__class__.__name__)


def _local_user_id_or_none(request: Request) -> str | None:
    return current_user_id(request)


def _required_user_id(request: Request) -> str:
    user_id = _local_user_id_or_none(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
        )
    return user_id


def _require_trip_store() -> TripPlanStore:
    if not trip_plan_store:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "TRIP_STORE_UNAVAILABLE", "message": "Trip store is not configured"},
        )
    return trip_plan_store


def _assert_expected_version(saved_trip_plan: SavedTripPlan, expected_version: int) -> None:
    if expected_version != saved_trip_plan.version:
        raise _version_conflict()


def _trip_plan_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "TRIP_PLAN_NOT_FOUND", "message": "Trip plan not found"},
    )


def _version_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "TRIP_PLAN_VERSION_CONFLICT",
            "message": "Trip plan was updated elsewhere; reload it before saving",
        },
    )


def _download_filename(title: str) -> str:
    safe_title = "".join(character if character.isascii() and character.isalnum() else "-" for character in title.lower())
    safe_title = "-".join(part for part in safe_title.split("-") if part)
    return f"{safe_title or 'trip-plan'}.md"


def _content_disposition_for_download(title: str) -> str:
    ascii_filename = _download_filename(title)
    utf8_filename = quote(f"{title.strip() or 'trip-plan'}.md")
    return f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"


async def _runtime_json(request: Request, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = dict(INTERNAL_SERVICE_HEADERS)
    user_id = _local_user_id_or_none(request)
    if user_id:
        headers["X-User-Id"] = user_id
    request_id = _request_id(request)
    if request_id:
        headers["X-Request-ID"] = request_id
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{AGENT_RUNTIME_URL}{path}", json=payload, headers=headers)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=_error_detail(response))
    parsed = response.json()
    return parsed if isinstance(parsed, dict) else {}


def _runtime_json_sync(path: str, payload: dict[str, Any], *, user_id: str, request_id: str | None) -> dict[str, Any]:
    headers = dict(INTERNAL_SERVICE_HEADERS)
    headers["X-User-Id"] = user_id
    if request_id:
        headers["X-Request-ID"] = request_id
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.post(f"{AGENT_RUNTIME_URL}{path}", json=payload, headers=headers)
    response.raise_for_status()
    parsed = response.json()
    return parsed if isinstance(parsed, dict) else {}


def _request_id(request: Request) -> str | None:
    return request.headers.get("X-Request-ID") or request.headers.get("x-request-id")


def _error_detail(response) -> Any:
    try:
        return response.json().get("detail", response.text)
    except ValueError:
        return response.text

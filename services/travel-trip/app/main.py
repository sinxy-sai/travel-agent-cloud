import os
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.proxy import check_upstream, proxy_request

from app.db import create_session_factory
from app.exporter import saved_trip_plan_to_markdown
from app.schemas import (
    SavedTripPlan,
    TripPlanCreateRequest,
    TripPlanInternalUpdateRequest,
    TripPlanListResponse,
    TripPlanRestoreRequest,
    TripPlanUpdateRequest,
    TripPlanVersionListResponse,
)
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
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
trip_plan_store = TripPlanStore(session_factory) if session_factory else None

app = FastAPI(title=APP_NAME, version="0.1.0")
add_cors(app, allowed_origins=ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await _check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] and trip_plan_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "trip-api-service-with-runtime-fallback",
        "databaseEnabled": trip_plan_store is not None,
        "upstreams": {"agentRuntime": upstream},
    }


@app.api_route("/api/v1/trip-plan", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/trip-plan")


@app.api_route("/api/v1/trip-plan-jobs", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_jobs_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/trip-plan-jobs")


@app.api_route("/api/v1/trip-plan-jobs/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_jobs(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/trip-plan-jobs/{path}")


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
        user_id = _local_user_id_or_none(request)
        if user_id and trip_plan_store:
            return trip_plan_store.list(user_id, page, page_size, favorite_only, query)
    return await _proxy(request, "/api/v1/trip-plans")


@app.get("/api/v1/trip-plans/{trip_plan_id}/versions", response_model=TripPlanVersionListResponse)
async def list_trip_plan_versions(
    trip_plan_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> Any:
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}/versions")
    try:
        return trip_plan_store.list_versions(user_id, trip_plan_id, page, page_size)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc


@app.post("/api/v1/trip-plans/{trip_plan_id}/versions/{version_id}/restore", response_model=SavedTripPlan)
async def restore_trip_plan_version(
    trip_plan_id: str,
    version_id: str,
    payload: TripPlanRestoreRequest,
    request: Request,
) -> Any:
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}/versions/{version_id}/restore")
    try:
        return trip_plan_store.restore_version(user_id, trip_plan_id, version_id, payload.expected_version)
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
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}/export")
    try:
        saved_trip_plan = trip_plan_store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    return PlainTextResponse(
        content=saved_trip_plan_to_markdown(saved_trip_plan),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition_for_download(saved_trip_plan.title)},
    )


@app.post("/api/v1/trip-plans/{trip_plan_id}/revise")
async def proxy_trip_plan_revise(trip_plan_id: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}/revise")


@app.post("/api/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate")
async def proxy_trip_plan_day_regenerate(trip_plan_id: str, day: int, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}/days/{day}/regenerate")


@app.get("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
async def get_trip_plan(trip_plan_id: str, request: Request) -> Any:
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}")
    try:
        return trip_plan_store.get(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc


@app.patch("/api/v1/trip-plans/{trip_plan_id}", response_model=SavedTripPlan)
async def update_trip_plan(
    trip_plan_id: str,
    payload: TripPlanUpdateRequest,
    request: Request,
) -> Any:
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}")
    try:
        return trip_plan_store.update(user_id, trip_plan_id, payload)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    except TripPlanVersionConflictError as exc:
        raise _version_conflict() from exc


@app.delete("/api/v1/trip-plans/{trip_plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip_plan(trip_plan_id: str, request: Request) -> Response:
    user_id = _local_user_id_or_none(request)
    if not user_id or not trip_plan_store:
        return await _proxy(request, f"/api/v1/trip-plans/{trip_plan_id}")
    try:
        trip_plan_store.delete(user_id, trip_plan_id)
    except TripPlanNotFoundError as exc:
        raise _trip_plan_not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _check_upstream(url: str) -> dict[str, Any]:
    return await check_upstream(url)


def _local_user_id_or_none(request: Request) -> str | None:
    return current_user_id(request)


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


async def _proxy(request: Request, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=AGENT_RUNTIME_URL,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-trip",
    )

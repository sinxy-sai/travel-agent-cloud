import os
from typing import Any

from fastapi import FastAPI, Request, Response
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.proxy import check_upstream, proxy_request

from app.db import create_session_factory
from app.profiles import UserProfileStore
from app.schemas import UserProfile, UserProfileUpdateRequest
from app.users import local_anonymous_user_id


APP_NAME = "Travel Auth Service"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AUTH_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = allowed_origins_from_env()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
session_factory = create_session_factory(DATABASE_URL) if DATABASE_URL else None
profile_store = UserProfileStore(session_factory) if session_factory else None

app = FastAPI(title=APP_NAME, version="0.1.0")
add_cors(app, allowed_origins=ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] and profile_store is not None else "degraded",
        "service": APP_NAME,
        "mode": "auth-api-service-with-runtime-fallback",
        "databaseEnabled": profile_store is not None,
        "upstreams": {"agentRuntime": upstream},
    }


@app.api_route("/api/v1/auth", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/auth")


@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/auth/{path}")


@app.api_route("/api/v1/me", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/me")


@app.get("/api/v1/me/profile", response_model=UserProfile)
async def get_profile(request: Request) -> Any:
    user_id = local_anonymous_user_id(request)
    if not user_id or not profile_store:
        return await _proxy(request, "/api/v1/me/profile")
    return profile_store.get(user_id)


@app.patch("/api/v1/me/profile", response_model=UserProfile)
async def update_profile(payload: UserProfileUpdateRequest, request: Request) -> Any:
    user_id = local_anonymous_user_id(request)
    if not user_id or not profile_store:
        return await _proxy(request, "/api/v1/me/profile")
    return profile_store.update(user_id, payload)


@app.api_route("/api/v1/me/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/me/{path}")


async def _proxy(request: Request, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=AGENT_RUNTIME_URL,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-auth",
    )

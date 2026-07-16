import os
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from travel_common.proxy import check_upstream, proxy_request


APP_NAME = "Travel Auth Service"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AUTH_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] else "degraded",
        "service": APP_NAME,
        "mode": "auth-api-facade",
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

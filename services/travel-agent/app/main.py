import os
from typing import Any

from fastapi import FastAPI, Request, Response
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.proxy import check_upstream, proxy_request


APP_NAME = "Travel Agent Facade"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("AGENT_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = allowed_origins_from_env()

app = FastAPI(title=APP_NAME, version="0.1.0")
add_cors(app, allowed_origins=ALLOWED_ORIGINS)


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream = await check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] else "degraded",
        "service": APP_NAME,
        "mode": "agent-api-facade",
        "upstreams": {"agentRuntime": upstream},
    }


@app.api_route("/api/v1/chat", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_chat(request: Request) -> Response:
    return await _proxy(request, "/api/v1/chat")


@app.api_route("/api/v1/agent", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/agent")


@app.api_route("/api/v1/agent/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/agent/{path}")


@app.api_route("/api/v1/conversations", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_conversations_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/conversations")


@app.api_route("/api/v1/conversations/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_conversations(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/conversations/{path}")


async def _proxy(request: Request, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=AGENT_RUNTIME_URL,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-agent",
    )

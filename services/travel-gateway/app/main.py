import os
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware


APP_NAME = "Travel Agent Gateway"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
TRAVEL_MCP_URL = os.getenv("TRAVEL_MCP_URL", "http://travel-mcp:8100").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_REQUEST_TIMEOUT_SECONDS", "180"))
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


@app.get("/gateway/health")
async def gateway_health() -> dict[str, Any]:
    checks = {
        "agentRuntime": await _check_upstream(f"{AGENT_RUNTIME_URL}/health"),
        "travelMcp": await _check_upstream(f"{TRAVEL_MCP_URL}/health"),
    }
    status = "ok" if checks["agentRuntime"]["ok"] else "degraded"
    return {
        "status": status,
        "service": APP_NAME,
        "upstreams": checks,
    }


@app.api_route("/health", methods=["GET", "HEAD"])
async def proxy_agent_health(request: Request) -> Response:
    return await _proxy(request, AGENT_RUNTIME_URL, "/health")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent_api(path: str, request: Request) -> Response:
    return await _proxy(request, AGENT_RUNTIME_URL, f"/api/{path}")


@app.api_route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent_api_root(request: Request) -> Response:
    return await _proxy(request, AGENT_RUNTIME_URL, "/api")


@app.api_route("/mcp", methods=["GET", "POST", "OPTIONS"])
async def proxy_mcp(request: Request) -> Response:
    return await _proxy(request, TRAVEL_MCP_URL, "/mcp")


@app.api_route("/tools/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_tools(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_MCP_URL, f"/tools/{path}")


@app.api_route("/tools", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_tools_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_MCP_URL, "/tools")


async def _check_upstream(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(url)
        return {"ok": response.status_code < 500, "statusCode": response.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": exc.__class__.__name__}


async def _proxy(request: Request, upstream_base_url: str, path: str) -> Response:
    headers = _forward_headers(request)
    body = await request.body()
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        upstream_response = await client.request(
            request.method,
            f"{upstream_base_url}{path}",
            params=request.query_params,
            content=body,
            headers=headers,
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_response_headers(upstream_response),
        media_type=upstream_response.headers.get("content-type"),
    )


def _forward_headers(request: Request) -> dict[str, str]:
    skipped = {"host", "content-length", "connection"}
    headers = {key: value for key, value in request.headers.items() if key.lower() not in skipped}
    client_host = request.client.host if request.client else ""
    if client_host:
        existing_forwarded_for = headers.get("x-forwarded-for")
        headers["x-forwarded-for"] = (
            f"{existing_forwarded_for}, {client_host}" if existing_forwarded_for else client_host
        )
        headers["x-real-ip"] = client_host
    headers["x-forwarded-proto"] = request.url.scheme
    return headers


def _response_headers(response: httpx.Response) -> dict[str, str]:
    skipped = {
        "content-encoding",
        "content-length",
        "connection",
        "transfer-encoding",
    }
    return {key: value for key, value in response.headers.items() if key.lower() not in skipped}

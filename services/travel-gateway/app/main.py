import os
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from travel_common.proxy import check_upstream, proxy_request


APP_NAME = "Travel Agent Gateway"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
TRAVEL_TRIP_URL = os.getenv("TRAVEL_TRIP_URL", "http://travel-trip:8200").rstrip("/")
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
        "travelTrip": await _check_upstream(f"{TRAVEL_TRIP_URL}/health"),
        "travelMcp": await _check_upstream(f"{TRAVEL_MCP_URL}/health"),
    }
    required_upstreams = ("agentRuntime", "travelTrip")
    status = "ok" if all(checks[name]["ok"] for name in required_upstreams) else "degraded"
    return {
        "status": status,
        "service": APP_NAME,
        "upstreams": checks,
    }


@app.api_route("/health", methods=["GET", "HEAD"])
async def proxy_agent_health(request: Request) -> Response:
    return await _proxy(request, AGENT_RUNTIME_URL, "/health")


@app.api_route("/api/v1/trip-plan", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_TRIP_URL, "/api/v1/trip-plan")


@app.api_route("/api/v1/trip-plan-jobs", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_jobs_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_TRIP_URL, "/api/v1/trip-plan-jobs")


@app.api_route("/api/v1/trip-plan-jobs/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plan_jobs(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_TRIP_URL, f"/api/v1/trip-plan-jobs/{path}")


@app.api_route("/api/v1/trip-plans", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plans_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_TRIP_URL, "/api/v1/trip-plans")


@app.api_route("/api/v1/trip-plans/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plans(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_TRIP_URL, f"/api/v1/trip-plans/{path}")


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
    return await check_upstream(url)


async def _proxy(request: Request, upstream_base_url: str, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=upstream_base_url,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
    )

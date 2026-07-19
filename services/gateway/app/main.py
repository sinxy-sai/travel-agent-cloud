import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import redis.asyncio as redis
from redis.exceptions import RedisError
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from travel_common.app import add_cors, allowed_origins_from_env
from travel_common.internal_auth import RequestContextMiddleware, internal_service_headers
from travel_common.metrics import add_metrics
from travel_common.proxy import check_upstream, proxy_request
from travel_common.tracing import add_tracing


APP_NAME = "Travel Agent Gateway"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
TRAVEL_AUTH_URL = os.getenv("TRAVEL_AUTH_URL", "http://travel-auth:8300").rstrip("/")
TRAVEL_TRIP_URL = os.getenv("TRAVEL_TRIP_URL", "http://travel-trip:8200").rstrip("/")
TRAVEL_AGENT_URL = os.getenv("TRAVEL_AGENT_URL", "http://travel-agent:8400").rstrip("/")
TRAVEL_MCP_URL = os.getenv("TRAVEL_MCP_URL", "http://travel-mcp:8100").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_REQUEST_TIMEOUT_SECONDS", "180"))
ALLOWED_ORIGINS = allowed_origins_from_env()
INTERNAL_SERVICE_HEADERS = internal_service_headers()
REDIS_RATE_LIMIT_ENABLED = os.getenv("REDIS_RATE_LIMIT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
REDIS_URL = os.getenv("REDIS_URL", "").strip()
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("GATEWAY_RATE_LIMIT_MAX_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GATEWAY_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_EXEMPT_PATHS = {"/health", "/gateway/health", "/metrics"}


class RedisRateLimiter:
    def __init__(self, redis_url: str, max_requests: int, window_seconds: int) -> None:
        self.enabled = REDIS_RATE_LIMIT_ENABLED and bool(redis_url)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True) if self.enabled else None

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except RedisError:
            return False

    async def allow(self, key: str) -> tuple[bool, int]:
        if self._client is None:
            return True, 0
        window = int(time.time()) // max(self.window_seconds, 1)
        redis_key = f"gateway:rate-limit:{window}:{key}"
        try:
            count = await self._client.incr(redis_key)
            if count == 1:
                await self._client.expire(redis_key, self.window_seconds + 5)
            retry_after = max(((window + 1) * self.window_seconds) - int(time.time()), 1)
            return count <= self.max_requests, retry_after
        except RedisError:
            return True, 0


rate_limiter = RedisRateLimiter(
    REDIS_URL,
    max_requests=RATE_LIMIT_MAX_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not rate_limiter.enabled or request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        allowed, retry_after = await rate_limiter.allow(_rate_limit_key(request))
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


app = FastAPI(title=APP_NAME, version="0.1.0")
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RedisRateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
add_cors(app, allowed_origins=ALLOWED_ORIGINS)
add_metrics(app, service_name="travel-gateway")
add_tracing(app, service_name="travel-gateway")


@app.api_route("/health", methods=["GET", "HEAD"])
@app.get("/gateway/health")
async def gateway_health() -> dict[str, Any]:
    return await _gateway_health_payload()


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


@app.api_route("/api/v1/auth", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_AUTH_URL, "/api/v1/auth")


@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_auth(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_AUTH_URL, f"/api/v1/auth/{path}")


@app.api_route("/api/v1/me", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_AUTH_URL, "/api/v1/me")


@app.api_route("/api/v1/me/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_me(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_AUTH_URL, f"/api/v1/me/{path}")


@app.api_route("/api/v1/chat", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_chat(request: Request) -> Response:
    return await _proxy(request, TRAVEL_AGENT_URL, "/api/v1/chat")


@app.api_route("/api/v1/agent", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_AGENT_URL, "/api/v1/agent")


@app.api_route("/api/v1/agent/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_agent(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_AGENT_URL, f"/api/v1/agent/{path}")


@app.api_route("/api/v1/conversations", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_conversations_root(request: Request) -> Response:
    return await _proxy(request, TRAVEL_AGENT_URL, "/api/v1/conversations")


@app.api_route("/api/v1/conversations/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_conversations(path: str, request: Request) -> Response:
    return await _proxy(request, TRAVEL_AGENT_URL, f"/api/v1/conversations/{path}")


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


async def _gateway_health_payload() -> dict[str, Any]:
    checks = {
        "agentRuntime": await _fetch_health(f"{AGENT_RUNTIME_URL}/health"),
        "travelAuth": await _fetch_health(f"{TRAVEL_AUTH_URL}/health"),
        "travelTrip": await _fetch_health(f"{TRAVEL_TRIP_URL}/health"),
        "travelAgent": await _fetch_health(f"{TRAVEL_AGENT_URL}/health"),
        "travelMcp": await _fetch_health(f"{TRAVEL_MCP_URL}/health"),
    }
    required_upstreams = ("agentRuntime", "travelAuth", "travelTrip", "travelAgent")
    status_value = "ok" if all(_healthy(checks[name]) for name in required_upstreams) else "degraded"

    runtime = _health_data(checks["agentRuntime"])
    auth = _health_data(checks["travelAuth"])
    trip = _health_data(checks["travelTrip"])
    agent = _health_data(checks["travelAgent"])
    redis_rate_limit_enabled = await rate_limiter.ping()

    return {
        "status": status_value,
        "service": APP_NAME,
        "env": runtime.get("env", os.getenv("APP_ENV", "local")),
        "llmEnabled": bool(runtime.get("llmEnabled", False)),
        "databaseEnabled": all(
            bool(service.get("databaseEnabled", False))
            for service in (auth, trip, agent)
        ),
        "messageQueueEnabled": bool(agent.get("messageQueueEnabled", False)),
        "redisRateLimitEnabled": redis_rate_limit_enabled,
        "objectStorageEnabled": bool(auth.get("objectStorageEnabled", False)),
        "githubOAuthEnabled": bool(auth.get("githubOAuthEnabled", False)),
        "agentEngine": str(runtime.get("agentEngine", "unknown")),
        "agentEngineCapabilities": runtime.get("agentEngineCapabilities", {}),
        "travelToolsProvider": str(runtime.get("travelToolsProvider", "unknown")),
        "ragEnabled": bool(runtime.get("ragEnabled", False)),
        "ragBackend": str(runtime.get("ragBackend", "unknown")),
        "upstreams": checks,
    }


async def _fetch_health(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(url)
        data: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                data = parsed
        except ValueError:
            data = {}
        return {
            "ok": response.status_code < 500,
            "statusCode": response.status_code,
            "status": data.get("status", "unknown"),
            "service": data.get("service", ""),
            "data": data,
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "status": "unreachable", "error": exc.__class__.__name__, "data": {}}


def _healthy(check: dict[str, Any]) -> bool:
    return bool(check.get("ok")) and check.get("status") == "ok"


def _health_data(check: dict[str, Any]) -> dict[str, Any]:
    data = check.get("data", {})
    return data if isinstance(data, dict) else {}


def _rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    parsed_host = urlparse(str(request.url)).hostname
    return parsed_host or "unknown"


async def _proxy(request: Request, upstream_base_url: str, path: str) -> Response:
    return await proxy_request(
        request,
        upstream_base_url=upstream_base_url,
        path=path,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        service_boundary="travel-gateway",
        extra_headers=INTERNAL_SERVICE_HEADERS,
    )

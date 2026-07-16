import os
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware


APP_NAME = "Travel Trip Service"
AGENT_RUNTIME_URL = os.getenv("AGENT_RUNTIME_URL", "http://agent-runtime:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("TRIP_SERVICE_REQUEST_TIMEOUT_SECONDS", "180"))
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
    upstream = await _check_upstream(f"{AGENT_RUNTIME_URL}/health")
    return {
        "status": "ok" if upstream["ok"] else "degraded",
        "service": APP_NAME,
        "mode": "trip-api-facade",
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


@app.api_route("/api/v1/trip-plans", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plans_root(request: Request) -> Response:
    return await _proxy(request, "/api/v1/trip-plans")


@app.api_route("/api/v1/trip-plans/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_trip_plans(path: str, request: Request) -> Response:
    return await _proxy(request, f"/api/v1/trip-plans/{path}")


async def _check_upstream(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(url)
        return {"ok": response.status_code < 500, "statusCode": response.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": exc.__class__.__name__}


async def _proxy(request: Request, path: str) -> Response:
    body = await request.body()
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        upstream_response = await client.request(
            request.method,
            f"{AGENT_RUNTIME_URL}{path}",
            params=request.query_params,
            content=body,
            headers=_forward_headers(request),
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
    headers["x-travel-service-boundary"] = "travel-trip"
    return headers


def _response_headers(response: httpx.Response) -> dict[str, str]:
    skipped = {
        "content-encoding",
        "content-length",
        "connection",
        "transfer-encoding",
    }
    return {key: value for key, value in response.headers.items() if key.lower() not in skipped}

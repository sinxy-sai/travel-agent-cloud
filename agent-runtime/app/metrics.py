from __future__ import annotations

import re
from time import perf_counter

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest


_DYNAMIC_SEGMENT_PATTERN = re.compile(r"^[0-9a-fA-F-]{16,}$")


def add_metrics(app: FastAPI, *, service_name: str) -> None:
    if getattr(app.state, "prometheus_metrics_enabled", False):
        return

    registry = CollectorRegistry(auto_describe=True)
    request_count = Counter(
        "travel_http_requests_total",
        "Total HTTP requests handled by the service.",
        ("service", "method", "path", "status_code"),
        registry=registry,
    )
    request_latency = Histogram(
        "travel_http_request_duration_seconds",
        "HTTP request latency in seconds.",
        ("service", "method", "path"),
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
        registry=registry,
    )
    in_progress = Gauge(
        "travel_http_requests_in_progress",
        "HTTP requests currently in progress.",
        ("service", "method", "path"),
        registry=registry,
    )

    @app.middleware("http")
    async def prometheus_metrics_middleware(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        in_progress_path = _normalized_path(request)
        path = in_progress_path
        start = perf_counter()
        status_code = "500"
        in_progress.labels(service_name, method, in_progress_path).inc()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            path = _normalized_path(request)
            return response
        finally:
            elapsed = perf_counter() - start
            in_progress.labels(service_name, method, in_progress_path).dec()
            request_count.labels(service_name, method, path, status_code).inc()
            request_latency.labels(service_name, method, path).observe(elapsed)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    app.state.prometheus_metrics_enabled = True


def _normalized_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path

    parts = []
    for part in request.url.path.split("/"):
        if not part:
            continue
        if part.isdigit() or _DYNAMIC_SEGMENT_PATTERN.match(part):
            parts.append("{id}")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"

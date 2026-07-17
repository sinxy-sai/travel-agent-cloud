from typing import Any

import httpx
from fastapi import Request, Response


async def check_upstream(url: str, *, timeout_seconds: float = 3) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
        return {"ok": response.status_code < 500, "statusCode": response.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": exc.__class__.__name__}


async def proxy_request(
    request: Request,
    *,
    upstream_base_url: str,
    path: str,
    timeout_seconds: float,
    service_boundary: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    body = await request.body()
    timeout = httpx.Timeout(timeout_seconds)
    headers = forward_headers(request, service_boundary=service_boundary)
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        upstream_response = await client.request(
            request.method,
            f"{upstream_base_url.rstrip('/')}{path}",
            params=request.query_params,
            content=body,
            headers=headers,
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers(upstream_response),
        media_type=upstream_response.headers.get("content-type"),
    )


def forward_headers(request: Request, *, service_boundary: str | None = None) -> dict[str, str]:
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
    if service_boundary:
        headers["x-travel-service-boundary"] = service_boundary
    return headers


def response_headers(response: httpx.Response) -> dict[str, str]:
    skipped = {
        "content-encoding",
        "content-length",
        "connection",
        "transfer-encoding",
    }
    return {key: value for key, value in response.headers.items() if key.lower() not in skipped}

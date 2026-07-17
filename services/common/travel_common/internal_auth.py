import logging
import os
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from travel_common.proxy import request_id_from_request


INTERNAL_TOKEN_HEADER = "X-Travel-Internal-Token"
logger = logging.getLogger("travel_common.requests")


def internal_service_token(env_name: str = "INTERNAL_SERVICE_TOKEN") -> str:
    return os.getenv(env_name, "").strip()


def internal_service_headers(token: str | None = None) -> dict[str, str]:
    value = (token if token is not None else internal_service_token()).strip()
    if not value:
        return {}
    return {INTERNAL_TOKEN_HEADER: value}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request_id_from_request(request)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed request_id=%s method=%s path=%s elapsed_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                _elapsed_ms(started_at),
            )
            raise
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{_elapsed_ms(started_at):.2f}"
        return response


class InternalServiceAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        token: str,
        protected_prefixes: tuple[str, ...] = ("/internal/",),
        excluded_prefixes: tuple[str, ...] = ("/health",),
    ) -> None:
        super().__init__(app)
        self._token = token.strip()
        self._protected_prefixes = protected_prefixes
        self._excluded_prefixes = excluded_prefixes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if self._token and self._requires_internal_token(request):
            provided = request.headers.get(INTERNAL_TOKEN_HEADER, "")
            if not _constant_time_equal(provided, self._token):
                return Response(
                    content='{"detail":{"code":"INTERNAL_SERVICE_UNAUTHORIZED","message":"Internal service token is invalid or missing"}}',
                    status_code=401,
                    media_type="application/json",
                )
        return await call_next(request)

    def _requires_internal_token(self, request: Request) -> bool:
        if request.method == "OPTIONS":
            return False
        path = request.url.path
        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._excluded_prefixes):
            return False
        return any(path.startswith(prefix) for prefix in self._protected_prefixes)


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000

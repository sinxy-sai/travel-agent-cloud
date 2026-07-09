import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import Settings

logger = logging.getLogger("travel_agent_runtime.requests")


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = _request_id(request)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = _elapsed_ms(started_at)
            logger.exception(
                "request_failed request_id=%s method=%s path=%s elapsed_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = _elapsed_ms(started_at)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"

        if not _skip_success_log(request, response):
            logger.info(
                "request_completed request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )

        return response


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _request_id(request: Request) -> str:
    incoming_request_id = request.headers.get("x-request-id")
    if (
        incoming_request_id
        and len(incoming_request_id) <= 128
        and "\n" not in incoming_request_id
        and "\r" not in incoming_request_id
    ):
        return incoming_request_id
    return str(uuid4())


def _skip_success_log(request: Request, response: Response) -> bool:
    return request.url.path == "/health" and response.status_code < 400

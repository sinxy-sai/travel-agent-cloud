import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class InternalServiceAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        token: str,
        protected_prefixes: tuple[str, ...] = ("/internal/",),
    ) -> None:
        super().__init__(app)
        self._token = token.strip()
        self._protected_prefixes = protected_prefixes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if self._token and self._requires_internal_token(request):
            provided = request.headers.get("X-Travel-Internal-Token", "")
            if not hmac.compare_digest(provided.encode("utf-8"), self._token.encode("utf-8")):
                return Response(
                    content='{"detail":{"code":"INTERNAL_SERVICE_UNAUTHORIZED","message":"Internal service token is invalid or missing"}}',
                    status_code=401,
                    media_type="application/json",
                )
        return await call_next(request)

    def _requires_internal_token(self, request: Request) -> bool:
        if request.method == "OPTIONS":
            return False
        return any(request.url.path.startswith(prefix) for prefix in self._protected_prefixes)

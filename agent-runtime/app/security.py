import time
import hashlib
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class FixedWindowRateLimiter:
    distributed = False

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> RateLimitDecision:
        if self._max_attempts <= 0 or self._window_seconds <= 0:
            return RateLimitDecision(allowed=True)

        now = time.time()
        cutoff = now - self._window_seconds
        attempts = self._attempts[key]
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

        if len(attempts) >= self._max_attempts:
            retry_after = max(1, int(attempts[0] + self._window_seconds - now))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

        attempts.append(now)
        return RateLimitDecision(allowed=True)


class RedisFixedWindowRateLimiter:
    distributed = True

    def __init__(self, redis_url: str, max_attempts: int, window_seconds: int, key_prefix: str) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix.strip(":") or "travel-agent-cloud"
        self._fallback = FixedWindowRateLimiter(max_attempts, window_seconds)
        try:
            from redis import Redis
            from redis.exceptions import RedisError
        except ImportError as exc:
            raise RuntimeError("redis package is required when REDIS_URL is configured") from exc
        self._redis_error = RedisError
        self._client = Redis.from_url(redis_url, socket_connect_timeout=1.0, socket_timeout=1.0)

    def check(self, key: str) -> RateLimitDecision:
        if self._max_attempts <= 0 or self._window_seconds <= 0:
            return RateLimitDecision(allowed=True)

        now = time.time()
        window = int(now // self._window_seconds)
        redis_key = self._redis_key(key, window)
        try:
            count = int(self._client.incr(redis_key))
            if count == 1:
                self._client.expire(redis_key, self._window_seconds + 5)
        except self._redis_error:
            return self._fallback.check(key)
        if count <= self._max_attempts:
            return RateLimitDecision(allowed=True)

        retry_after = max(1, int((window + 1) * self._window_seconds - now))
        return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

    def _redis_key(self, key: str, window: int) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:rate-limit:{window}:{digest}"


def create_auth_rate_limiter(
    *,
    redis_url: str,
    max_attempts: int,
    window_seconds: int,
    key_prefix: str,
) -> FixedWindowRateLimiter | RedisFixedWindowRateLimiter:
    if redis_url.strip():
        return RedisFixedWindowRateLimiter(redis_url, max_attempts, window_seconds, key_prefix)
    return FixedWindowRateLimiter(max_attempts, window_seconds)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


def client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

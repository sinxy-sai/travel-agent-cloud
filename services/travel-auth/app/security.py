import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import UserSecurityEventRecord


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


class UserSecurityEventStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        user_id: str,
        event_type: str,
        *,
        client_identifier: str = "",
        details: dict | None = None,
    ) -> None:
        with session_scope(self._session_factory) as session:
            session.add(
                UserSecurityEventRecord(
                    user_id=user_id,
                    event_type=event_type,
                    client_id_hash=_hash_client_identifier(client_identifier),
                    details=details or {},
                    created_at=datetime.now(UTC),
                )
            )


def client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _hash_client_identifier(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

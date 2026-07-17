import hashlib
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import UserSecurityEventRecord
from app.schemas import UserSecurityEvent, UserSecurityEventListResponse


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

    def list(self, user_id: str, page: int, page_size: int) -> UserSecurityEventListResponse:
        safe_page = max(1, page)
        safe_page_size = min(max(1, page_size), 50)
        with session_scope(self._session_factory) as session:
            total_items = int(
                session.scalar(
                    select(func.count())
                    .select_from(UserSecurityEventRecord)
                    .where(UserSecurityEventRecord.user_id == user_id)
                )
                or 0
            )
            records = session.scalars(
                select(UserSecurityEventRecord)
                .where(UserSecurityEventRecord.user_id == user_id)
                .order_by(UserSecurityEventRecord.created_at.desc())
                .offset((safe_page - 1) * safe_page_size)
                .limit(safe_page_size)
            ).all()
        total_pages = max(1, (total_items + safe_page_size - 1) // safe_page_size)
        return UserSecurityEventListResponse(
            data=[_to_security_event(record) for record in records],
            page=safe_page,
            page_size=safe_page_size,
            total_items=total_items,
            total_pages=total_pages,
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


def _to_security_event(record: UserSecurityEventRecord) -> UserSecurityEvent:
    return UserSecurityEvent(
        id=record.id,
        event_type=record.event_type,
        details=record.details or {},
        created_at=record.created_at,
    )

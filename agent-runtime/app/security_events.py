import hashlib
from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import UserSecurityEventRecord
from app.schemas import UserSecurityEvent, UserSecurityEventListResponse


class UserSecurityEventStore:
    def __init__(self) -> None:
        self._events: dict[str, tuple[str, UserSecurityEvent]] = {}

    def record(
        self,
        user_id: str,
        event_type: str,
        *,
        client_identifier: str = "",
        details: dict | None = None,
    ) -> UserSecurityEvent:
        event = UserSecurityEvent(
            id=str(uuid4()),
            event_type=event_type,
            details=_safe_details(details or {}),
            created_at=_now(),
        )
        self._events[event.id] = (user_id, event)
        return event

    def list(self, user_id: str, page: int, page_size: int) -> UserSecurityEventListResponse:
        events = sorted(
            [event for owner_id, event in self._events.values() if owner_id == user_id],
            key=lambda event: event.created_at,
            reverse=True,
        )
        start = (page - 1) * page_size
        end = start + page_size
        total_items = len(events)
        return UserSecurityEventListResponse(
            data=events[start:end],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=ceil(total_items / page_size) if total_items else 0,
        )

    def delete_for_user(self, user_id: str) -> None:
        event_ids = [event_id for event_id, (owner_id, _event) in self._events.items() if owner_id == user_id]
        for event_id in event_ids:
            del self._events[event_id]


class DatabaseUserSecurityEventStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        user_id: str,
        event_type: str,
        *,
        client_identifier: str = "",
        details: dict | None = None,
    ) -> UserSecurityEvent:
        with session_scope(self._session_factory) as session:
            record = UserSecurityEventRecord(
                user_id=user_id,
                event_type=event_type,
                client_id_hash=_hash_client_identifier(client_identifier),
                details=_safe_details(details or {}),
            )
            session.add(record)
            session.flush()
            return _to_security_event(record)

    def list(self, user_id: str, page: int, page_size: int) -> UserSecurityEventListResponse:
        with session_scope(self._session_factory) as session:
            total_items = session.scalar(
                select(func.count()).select_from(UserSecurityEventRecord).where(UserSecurityEventRecord.user_id == user_id)
            )
            records = session.scalars(
                select(UserSecurityEventRecord)
                .where(UserSecurityEventRecord.user_id == user_id)
                .order_by(UserSecurityEventRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()

            total = int(total_items or 0)
            return UserSecurityEventListResponse(
                data=[_to_security_event(record) for record in records],
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=ceil(total / page_size) if total else 0,
            )

    def delete_for_user(self, user_id: str) -> None:
        with session_scope(self._session_factory) as session:
            session.execute(delete(UserSecurityEventRecord).where(UserSecurityEventRecord.user_id == user_id))


def _to_security_event(record: UserSecurityEventRecord) -> UserSecurityEvent:
    return UserSecurityEvent(
        id=record.id,
        event_type=record.event_type,
        details=dict(record.details or {}),
        created_at=record.created_at,
    )


def _safe_details(details: dict) -> dict:
    safe: dict[str, str | int | bool] = {}
    for key, value in details.items():
        if not isinstance(key, str) or key.lower() in {"password", "token", "secret", "api_key"}:
            continue
        if isinstance(value, bool | int):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:120]
    return safe


def _hash_client_identifier(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)

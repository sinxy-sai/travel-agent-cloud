from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import UserProfileRecord
from app.schemas import UserProfile, UserProfileUpdateRequest


class UserProfileStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, user_id: str) -> UserProfile:
        with session_scope(self._session_factory) as session:
            record = _get_or_create_record(session, user_id)
            session.flush()
            return _to_profile(record)

    def update(self, user_id: str, request: UserProfileUpdateRequest) -> UserProfile:
        with session_scope(self._session_factory) as session:
            record = _get_or_create_record(session, user_id)
            changes = request.model_dump(exclude_unset=True)
            for field in ("display_name", "home_city", "preferred_budget", "travel_style"):
                value = changes.get(field)
                if value is not None:
                    setattr(record, field, value)
            if "interests" in changes and changes["interests"] is not None:
                record.interests = changes["interests"]
            record.updated_at = _now()
            session.flush()
            return _to_profile(record)


def _get_or_create_record(session: Session, user_id: str) -> UserProfileRecord:
    record = session.scalar(select(UserProfileRecord).where(UserProfileRecord.user_id == user_id))
    if record is not None:
        return record
    record = UserProfileRecord(user_id=user_id, interests=[])
    session.add(record)
    return record


def _to_profile(record: UserProfileRecord) -> UserProfile:
    return UserProfile(
        user_id=record.user_id,
        display_name=record.display_name,
        home_city=record.home_city,
        preferred_budget=record.preferred_budget,
        travel_style=record.travel_style,
        interests=list(record.interests or []),
        updated_at=record.updated_at,
    )


def _now() -> datetime:
    return datetime.now(UTC)

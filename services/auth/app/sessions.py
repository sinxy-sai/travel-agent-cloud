import hashlib
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import AuthSessionRecord
from app.schemas import AuthSessionInfo


class AuthSessionNotFoundError(Exception):
    pass


class AuthSessionRevokedError(Exception):
    pass


class AuthSessionStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        user_id: str,
        expires_at: datetime,
        *,
        client_identifier: str = "",
        user_agent: str = "",
    ) -> AuthSessionInfo:
        with session_scope(self._session_factory) as session:
            record = AuthSessionRecord(
                user_id=user_id,
                client_id_hash=_hash_client_identifier(client_identifier),
                user_agent=_safe_user_agent(user_agent),
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
            return _to_auth_session_info(record)

    def list_for_user(self, user_id: str, current_session_id: str | None = None) -> list[AuthSessionInfo]:
        with session_scope(self._session_factory) as session:
            records = session.scalars(
                select(AuthSessionRecord)
                .where(AuthSessionRecord.user_id == user_id)
                .order_by(AuthSessionRecord.created_at.desc())
            ).all()
            return [_to_auth_session_info(record, current_session_id) for record in records]

    def require_active(self, user_id: str, session_id: str, now: datetime | None = None) -> AuthSessionInfo:
        current_time = now or _now()
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.id == session_id,
                    AuthSessionRecord.user_id == user_id,
                )
            )
            if record is None:
                raise AuthSessionNotFoundError(session_id)
            revoked_at = _as_utc(record.revoked_at)
            expires_at = _as_utc(record.expires_at)
            if revoked_at is not None or expires_at <= current_time:
                raise AuthSessionRevokedError(session_id)
            record.last_seen_at = current_time
            session.flush()
            return _to_auth_session_info(record, session_id)

    def revoke(self, user_id: str, session_id: str) -> AuthSessionInfo:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.id == session_id,
                    AuthSessionRecord.user_id == user_id,
                )
            )
            if record is None:
                raise AuthSessionNotFoundError(session_id)
            if record.revoked_at is None:
                record.revoked_at = _now()
                session.flush()
            return _to_auth_session_info(record, session_id)

    def revoke_all(self, user_id: str, except_session_id: str | None = None) -> int:
        with session_scope(self._session_factory) as session:
            statement = (
                update(AuthSessionRecord)
                .where(AuthSessionRecord.user_id == user_id)
                .where(AuthSessionRecord.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
            if except_session_id:
                statement = statement.where(AuthSessionRecord.id != except_session_id)
            result = session.execute(statement)
            return int(result.rowcount or 0)


def _to_auth_session_info(record: AuthSessionRecord, current_session_id: str | None = None) -> AuthSessionInfo:
    return AuthSessionInfo(
        id=record.id,
        user_id=record.user_id,
        user_agent=record.user_agent,
        current=record.id == current_session_id,
        revoked=record.revoked_at is not None,
        created_at=record.created_at,
        last_seen_at=record.last_seen_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
    )


def _safe_user_agent(value: str) -> str:
    return value.strip().replace("\r", " ").replace("\n", " ")[:240]


def _hash_client_identifier(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value

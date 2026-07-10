import hashlib
from datetime import UTC, datetime
from uuid import uuid4

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
    def __init__(self) -> None:
        self._sessions: dict[str, AuthSessionInfo] = {}

    def create(
        self,
        user_id: str,
        expires_at: datetime,
        *,
        client_identifier: str = "",
        user_agent: str = "",
    ) -> AuthSessionInfo:
        now = _now()
        session = AuthSessionInfo(
            id=str(uuid4()),
            user_id=user_id,
            user_agent=_safe_user_agent(user_agent),
            current=False,
            revoked=False,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
        self._sessions[session.id] = session
        return session

    def list_for_user(self, user_id: str, current_session_id: str | None = None) -> list[AuthSessionInfo]:
        sessions = [
            session.model_copy(
                update={
                    "current": session.id == current_session_id,
                    "revoked": session.revoked_at is not None,
                }
            )
            for session in self._sessions.values()
            if session.user_id == user_id
        ]
        return sorted(sessions, key=lambda session: session.created_at, reverse=True)

    def require_active(self, user_id: str, session_id: str, now: datetime | None = None) -> AuthSessionInfo:
        session = self._sessions.get(session_id)
        current_time = now or _now()
        if session is None or session.user_id != user_id:
            raise AuthSessionNotFoundError(session_id)
        if session.revoked_at is not None or session.expires_at <= current_time:
            raise AuthSessionRevokedError(session_id)
        updated = session.model_copy(update={"last_seen_at": current_time, "current": True})
        self._sessions[session_id] = updated
        return updated

    def revoke(self, user_id: str, session_id: str) -> AuthSessionInfo:
        session = self._sessions.get(session_id)
        if session is None or session.user_id != user_id:
            raise AuthSessionNotFoundError(session_id)
        if session.revoked_at is None:
            session = session.model_copy(update={"revoked_at": _now(), "revoked": True})
            self._sessions[session_id] = session
        return session

    def revoke_all(self, user_id: str, except_session_id: str | None = None) -> int:
        revoked = 0
        now = _now()
        for session_id, session in list(self._sessions.items()):
            if session.user_id != user_id or session_id == except_session_id or session.revoked_at is not None:
                continue
            self._sessions[session_id] = session.model_copy(update={"revoked_at": now, "revoked": True})
            revoked += 1
        return revoked


class DatabaseAuthSessionStore:
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
            if record.revoked_at is not None or record.expires_at <= current_time:
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


def _to_auth_session_info(
    record: AuthSessionRecord,
    current_session_id: str | None = None,
) -> AuthSessionInfo:
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

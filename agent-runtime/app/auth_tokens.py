import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import AuthTokenRecord

TOKEN_PURPOSE_EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
TOKEN_PURPOSE_PASSWORD_RESET = "PASSWORD_RESET"


class AuthTokenError(Exception):
    pass


class InvalidAuthTokenError(AuthTokenError):
    pass


@dataclass(frozen=True)
class GeneratedAuthToken:
    token: str
    expires_at: datetime


class AuthTokenStore:
    def __init__(self) -> None:
        self._tokens_by_hash: dict[str, tuple[str, str, datetime, datetime | None]] = {}

    def create(self, user_id: str, purpose: str, ttl_seconds: int) -> GeneratedAuthToken:
        generated = _generate(ttl_seconds)
        self._tokens_by_hash[_hash_token(generated.token)] = (user_id, purpose, generated.expires_at, None)
        return generated

    def consume(self, token: str, purpose: str) -> str:
        token_hash = _hash_token(token)
        item = self._tokens_by_hash.get(token_hash)
        now = _now()
        if item is None:
            raise InvalidAuthTokenError()
        user_id, stored_purpose, expires_at, consumed_at = item
        if stored_purpose != purpose or consumed_at is not None or _is_expired(expires_at, now):
            raise InvalidAuthTokenError()
        self._tokens_by_hash[token_hash] = (user_id, stored_purpose, expires_at, now)
        return user_id


class DatabaseAuthTokenStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, user_id: str, purpose: str, ttl_seconds: int) -> GeneratedAuthToken:
        generated = _generate(ttl_seconds)
        with session_scope(self._session_factory) as session:
            record = AuthTokenRecord(
                user_id=user_id,
                purpose=purpose,
                token_hash=_hash_token(generated.token),
                expires_at=generated.expires_at,
            )
            session.add(record)
        return generated

    def consume(self, token: str, purpose: str) -> str:
        token_hash = _hash_token(token)
        now = _now()
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AuthTokenRecord)
                .where(
                    AuthTokenRecord.token_hash == token_hash,
                    AuthTokenRecord.purpose == purpose,
                )
                .limit(1)
            )
            if record is None or record.consumed_at is not None or _is_expired(record.expires_at, now):
                raise InvalidAuthTokenError()
            record.consumed_at = now
            session.flush()
            return record.user_id


def _generate(ttl_seconds: int) -> GeneratedAuthToken:
    return GeneratedAuthToken(
        token=secrets.token_urlsafe(32),
        expires_at=_now() + timedelta(seconds=ttl_seconds),
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import AuthIdentityRecord
from app.schemas import AuthIdentity


class AuthIdentityConflictError(Exception):
    pass


class AuthIdentityNotFoundError(Exception):
    pass


class AuthIdentityStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_for_user(self, user_id: str) -> list[AuthIdentity]:
        with session_scope(self._session_factory) as session:
            records = session.scalars(
                select(AuthIdentityRecord)
                .where(AuthIdentityRecord.user_id == user_id)
                .order_by(AuthIdentityRecord.created_at)
            ).all()
            return [_to_auth_identity(record) for record in records]

    def get_by_provider_user_id(self, provider: str, provider_user_id: str) -> AuthIdentity:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == provider,
                    AuthIdentityRecord.provider_user_id == provider_user_id,
                )
            )
            if record is None:
                raise AuthIdentityNotFoundError(provider)
            return _to_auth_identity(record)

    def upsert(
        self,
        user_id: str,
        provider: str,
        provider_user_id: str,
        email: str = "",
        display_name: str = "",
        avatar_url: str = "",
    ) -> AuthIdentity:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(AuthIdentityRecord).where(
                    AuthIdentityRecord.provider == provider,
                    AuthIdentityRecord.provider_user_id == provider_user_id,
                )
            )
            if record is not None:
                if record.user_id != user_id:
                    raise AuthIdentityConflictError(provider)
                record.email = email.strip().lower()
                record.display_name = display_name.strip()
                record.avatar_url = avatar_url.strip()
                record.updated_at = _now()
                session.flush()
                return _to_auth_identity(record)

            record = AuthIdentityRecord(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
                email=email.strip().lower(),
                display_name=display_name.strip(),
                avatar_url=avatar_url.strip(),
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError as exc:
                raise AuthIdentityConflictError(provider) from exc
            return _to_auth_identity(record)

    def delete_for_user(self, user_id: str, provider: str) -> None:
        with session_scope(self._session_factory) as session:
            result = session.execute(
                delete(AuthIdentityRecord).where(
                    AuthIdentityRecord.user_id == user_id,
                    AuthIdentityRecord.provider == provider,
                )
            )
            if result.rowcount == 0:
                raise AuthIdentityNotFoundError(provider)


def _to_auth_identity(record: AuthIdentityRecord) -> AuthIdentity:
    return AuthIdentity(
        id=record.id,
        user_id=record.user_id,
        provider=record.provider,
        provider_user_id=record.provider_user_id,
        email=record.email,
        display_name=record.display_name,
        avatar_url=record.avatar_url,
        created_at=record.created_at,
    )


def _now() -> datetime:
    return datetime.now(UTC)

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_created", "user_id", "created_at"),
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    client_id_hash: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthTokenRecord(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        Index("ix_auth_tokens_hash_purpose", "token_hash", "purpose"),
        Index("ix_auth_tokens_user_purpose_created", "user_id", "purpose", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthIdentityRecord(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        Index("ix_auth_identities_provider_user", "provider", "provider_user_id", unique=True),
        Index("ix_auth_identities_user_provider", "user_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), default="")
    display_name: Mapped[str] = mapped_column(String(120), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserSecurityEventRecord(Base):
    __tablename__ = "user_security_events"
    __table_args__ = (Index("ix_user_security_events_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    client_id_hash: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserProfileRecord(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), default="")
    home_city: Mapped[str] = mapped_column(String(80), default="")
    preferred_budget: Mapped[str] = mapped_column(String(40), default="")
    travel_style: Mapped[str] = mapped_column(String(80), default="")
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

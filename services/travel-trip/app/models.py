from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TripPlanRecord(Base):
    __tablename__ = "trip_plans"
    __table_args__ = (
        Index("ix_trip_plans_user_created", "user_id", "created_at"),
        Index("ix_trip_plans_user_favorite_created", "user_id", "is_favorite", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(80))
    days: Mapped[int] = mapped_column(Integer)
    budget: Mapped[str] = mapped_column(String(40))
    interests: Mapped[str] = mapped_column(String(300), default="")
    plan: Mapped[dict] = mapped_column(JSON)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TripPlanVersionRecord(Base):
    __tablename__ = "trip_plan_versions"
    __table_args__ = (
        Index("ix_trip_plan_versions_trip_plan_version", "trip_plan_id", "version", unique=True),
        Index("ix_trip_plan_versions_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True)
    trip_plan_id: Mapped[str] = mapped_column(ForeignKey("trip_plans.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    plan: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(40), default="manual_edit")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

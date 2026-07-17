from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.settings import Settings


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    normalized_url = _normalize_database_url(database_url)
    engine_kwargs = {"pool_pre_ping": True}
    if normalized_url == "sqlite+pysqlite:///:memory:":
        engine_kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    engine = create_engine(normalized_url, **engine_kwargs)
    Base.metadata.create_all(engine)
    _ensure_existing_schema(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def maybe_create_session_factory(settings: Settings) -> sessionmaker[Session] | None:
    if not settings.database_url:
        return None
    return create_session_factory(settings.database_url)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _ensure_existing_schema(engine) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        if inspector.has_table("trip_plans"):
            trip_plan_columns = {column["name"] for column in inspector.get_columns("trip_plans")}
            if "is_favorite" not in trip_plan_columns:
                connection.execute(text("ALTER TABLE trip_plans ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT FALSE"))
            if "version" not in trip_plan_columns:
                connection.execute(text("ALTER TABLE trip_plans ADD COLUMN version INTEGER NOT NULL DEFAULT 1"))
            if "updated_at" not in trip_plan_columns:
                connection.execute(text("ALTER TABLE trip_plans ADD COLUMN updated_at TIMESTAMP NULL"))
                connection.execute(text("UPDATE trip_plans SET updated_at = created_at WHERE updated_at IS NULL"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trip_plans_user_favorite_created "
                    "ON trip_plans (user_id, is_favorite, created_at)"
                )
            )
        if inspector.has_table("trip_plan_versions"):
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trip_plan_versions_trip_plan_version "
                    "ON trip_plan_versions (trip_plan_id, version)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trip_plan_versions_user_created "
                    "ON trip_plan_versions (user_id, created_at)"
                )
            )


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

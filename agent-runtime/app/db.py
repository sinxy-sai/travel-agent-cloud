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
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_trip_plans_user_favorite_created "
                    "ON trip_plans (user_id, is_favorite, created_at)"
                )
            )

        if inspector.has_table("users"):
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "email_verified" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
            if "email_verified_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP NULL"))


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

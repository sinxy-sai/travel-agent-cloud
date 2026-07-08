from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
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
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def maybe_create_session_factory(settings: Settings) -> sessionmaker[Session] | None:
    if not settings.database_url:
        return None
    return create_session_factory(settings.database_url)


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


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

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.planning_context import TravelPlanningContext
from app.schemas import TripPlanRequest, TripPlanResponse
from app.settings import Settings

try:
    from sqlalchemy import DateTime, Float, Index, String, Text, create_engine, or_, select
    from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
except ImportError:  # pragma: no cover - optional in local lightweight evals.
    DateTime = Float = Index = String = Text = None
    create_engine = or_ = select = None
    DeclarativeBase = object
    Mapped = mapped_column = sessionmaker = Session = None


@dataclass(frozen=True)
class KnowledgeHit:
    record_type: str
    title: str
    summary: str
    source: str = "runtime_static_knowledge"
    score: float = 0.0

    def to_prompt_line(self) -> str:
        return f"[{self.record_type}] {self.title}: {self.summary}"


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    hits: tuple[KnowledgeHit, ...]
    backend: str = "static"

    def to_trace_detail(self) -> str:
        types = ",".join(hit.record_type for hit in self.hits[:5]) if self.hits else "none"
        return f"backend={self.backend};hits={len(self.hits)};types={types}"


@dataclass(frozen=True)
class KnowledgeRecordView:
    id: str
    destination: str
    record_type: str
    title: str
    summary: str
    source: str
    score: float
    expires_at: str | None

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "id": self.id,
            "destination": self.destination,
            "recordType": self.record_type,
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "score": self.score,
            "expiresAt": self.expires_at,
        }


class KnowledgeRetriever:
    @property
    def backend(self) -> str:
        return "unknown"

    def retrieve(self, request: TripPlanRequest, context: TravelPlanningContext) -> KnowledgeRetrievalResult:
        raise NotImplementedError

    def remember_successful_plan(self, request: TripPlanRequest, plan: TripPlanResponse) -> None:
        return None

    def list_records(self, destination: str | None = None, limit: int = 20) -> tuple[KnowledgeRecordView, ...]:
        return ()

    def seed_destination_knowledge(self, destination: str) -> int:
        return 0


class StaticKnowledgeRetriever(KnowledgeRetriever):
    @property
    def backend(self) -> str:
        return "static"

    def retrieve(self, request: TripPlanRequest, context: TravelPlanningContext) -> KnowledgeRetrievalResult:
        hits = _static_hits(request, context)
        return KnowledgeRetrievalResult(hits=hits, backend="static")


if create_engine is not None:
    class Base(DeclarativeBase):
        pass


    class KnowledgeRecord(Base):
        __tablename__ = "agent_knowledge_records"
        __table_args__ = (
            Index("ix_agent_knowledge_records_destination_record_type", "destination", "record_type"),
            Index("ix_agent_knowledge_records_expires_at", "expires_at"),
        )

        id: Mapped[str] = mapped_column(String(80), primary_key=True)
        destination: Mapped[str] = mapped_column(String(120), index=True)
        record_type: Mapped[str] = mapped_column(String(80), index=True)
        title: Mapped[str] = mapped_column(String(240))
        summary: Mapped[str] = mapped_column(Text)
        source: Mapped[str] = mapped_column(String(120), default="agent_runtime")
        score: Mapped[float] = mapped_column(Float, default=0.5)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
        expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
else:
    Base = object
    KnowledgeRecord = None


class PostgresKnowledgeRetriever(KnowledgeRetriever):
    def __init__(self, database_url: str, fallback: KnowledgeRetriever | None = None) -> None:
        if create_engine is None or sessionmaker is None or KnowledgeRecord is None:
            raise RuntimeError("SQLAlchemy is not installed")
        self._fallback = fallback or StaticKnowledgeRetriever()
        self._session_factory = _create_session_factory(database_url)

    @property
    def backend(self) -> str:
        return "postgres"

    def retrieve(self, request: TripPlanRequest, context: TravelPlanningContext) -> KnowledgeRetrievalResult:
        now = datetime.now(UTC)
        static_hits = list(self._fallback.retrieve(request, context).hits)
        with self._session_factory() as session:
            filters = [
                KnowledgeRecord.destination.ilike(request.destination.strip()),
                or_(KnowledgeRecord.expires_at.is_(None), KnowledgeRecord.expires_at > now),
            ]
            keyword_filters = _keyword_filters(context)
            if keyword_filters is not None:
                filters.append(keyword_filters)
            records = list(
                session.execute(
                    select(KnowledgeRecord)
                    .where(*filters)
                    .order_by(KnowledgeRecord.score.desc(), KnowledgeRecord.updated_at.desc())
                    .limit(8)
                ).scalars()
            )
        db_hits = [
            KnowledgeHit(
                record_type=record.record_type,
                title=record.title,
                summary=record.summary[:700],
                source=record.source,
                score=record.score,
            )
            for record in records
        ]
        return KnowledgeRetrievalResult(hits=tuple(_dedupe_hits([*db_hits, *static_hits])[:5]), backend="postgres")

    def remember_successful_plan(self, request: TripPlanRequest, plan: TripPlanResponse) -> None:
        if not plan.days:
            return
        now = datetime.now(UTC)
        title = f"{request.destination} {request.days}-day itinerary summary"
        summary = _plan_summary(plan)
        with self._session_factory() as session:
            session.add(
                KnowledgeRecord(
                    id=str(uuid4()),
                    destination=request.destination.strip(),
                    record_type="itinerary_summary",
                    title=title[:240],
                    summary=summary,
                    source="agent_runtime_successful_plan",
                    score=0.6,
                    created_at=now,
                    updated_at=now,
                    expires_at=now + timedelta(days=90),
                )
            )
            session.commit()

    def list_records(self, destination: str | None = None, limit: int = 20) -> tuple[KnowledgeRecordView, ...]:
        limit = max(1, min(limit, 100))
        with self._session_factory() as session:
            statement = select(KnowledgeRecord).order_by(KnowledgeRecord.updated_at.desc()).limit(limit)
            if destination and destination.strip():
                statement = statement.where(KnowledgeRecord.destination.ilike(destination.strip()))
            records = list(session.execute(statement).scalars())
        return tuple(_record_to_view(record) for record in records)

    def seed_destination_knowledge(self, destination: str) -> int:
        now = datetime.now(UTC)
        hits = _static_destination_knowledge(destination)
        inserted = 0
        with self._session_factory() as session:
            for hit in hits:
                existing = session.execute(
                    select(KnowledgeRecord)
                    .where(KnowledgeRecord.destination.ilike(destination.strip()))
                    .where(KnowledgeRecord.record_type == hit.record_type)
                    .where(KnowledgeRecord.title == hit.title)
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    existing.summary = hit.summary
                    existing.source = "agent_runtime_seed"
                    existing.score = max(existing.score, hit.score)
                    existing.updated_at = now
                    existing.expires_at = now + timedelta(days=180)
                    continue
                session.add(
                    KnowledgeRecord(
                        id=str(uuid4()),
                        destination=destination.strip(),
                        record_type=hit.record_type,
                        title=hit.title[:240],
                        summary=hit.summary,
                        source="agent_runtime_seed",
                        score=hit.score,
                        created_at=now,
                        updated_at=now,
                        expires_at=now + timedelta(days=180),
                    )
                )
                inserted += 1
            session.commit()
        return inserted


def create_knowledge_retriever(settings: Settings) -> KnowledgeRetriever:
    fallback = StaticKnowledgeRetriever()
    if not settings.rag_enabled or not settings.database_url.strip():
        return fallback
    try:
        return PostgresKnowledgeRetriever(settings.database_url, fallback)
    except Exception:
        return fallback


def _create_session_factory(database_url: str):
    normalized = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(normalized, pool_pre_ping=True, connect_args={"connect_timeout": 2})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _keyword_filters(context: TravelPlanningContext):
    terms = [*context.interest_terms, *context.preference_terms, *context.style_tags]
    clauses = []
    for term in terms[:8]:
        normalized = term.strip()
        if not normalized:
            continue
        pattern = f"%{normalized}%"
        clauses.extend((KnowledgeRecord.title.ilike(pattern), KnowledgeRecord.summary.ilike(pattern)))
    return or_(*clauses) if clauses else None


def _static_hits(request: TripPlanRequest, context: TravelPlanningContext) -> tuple[KnowledgeHit, ...]:
    scored = sorted(
        ((_score_hit(hit, context), hit) for hit in _static_destination_knowledge(request.destination)),
        key=lambda item: item[0],
        reverse=True,
    )
    return tuple(hit for score, hit in scored if score > 0)[:5]


def _static_destination_knowledge(destination: str) -> tuple[KnowledgeHit, ...]:
    city = destination.strip().lower()
    generic = (
        KnowledgeHit(
            record_type="destination_note",
            title=f"{destination} pacing",
            summary="Keep transit buffers between major stops and avoid packing too many cross-city moves into one day.",
            score=0.2,
        ),
        KnowledgeHit(
            record_type="planning_pattern",
            title="weather-aware routing",
            summary="Put outdoor attractions earlier in the day and keep indoor alternatives for rain or extreme heat.",
            score=0.2,
        ),
    )
    city_notes: dict[str, tuple[KnowledgeHit, ...]] = {
        "chengdu": (
            KnowledgeHit("destination_note", "Chengdu food pacing", "Leave flexible dinner time around food districts and avoid scheduling spicy meals immediately before long transfers.", score=0.7),
            KnowledgeHit("destination_note", "Chengdu culture route", "Pair heritage sites with nearby tea houses or neighborhoods to keep the day walkable.", score=0.7),
        ),
        "shanghai": (
            KnowledgeHit("destination_note", "Shanghai family pacing", "For family trips, alternate museums, riverside walks, and mall-adjacent rest stops.", score=0.7),
        ),
        "hangzhou": (
            KnowledgeHit("destination_note", "Hangzhou lake routing", "Group West Lake-side stops by shore area to reduce repeated transfers.", score=0.7),
        ),
        "beijing": (
            KnowledgeHit("destination_note", "Beijing history route", "Historical routes need ticket and security buffer time; avoid more than two major heritage sites per day.", score=0.7),
        ),
        "xi'an": (
            KnowledgeHit("destination_note", "Xi'an short trip", "For one-day trips, combine one major heritage anchor with a compact food area instead of multiple distant sites.", score=0.7),
        ),
        "guangzhou": (
            KnowledgeHit("destination_note", "Guangzhou food route", "Food-focused plans work best when grouped by district and scheduled with late breakfast or dim sum flexibility.", score=0.7),
        ),
    }
    return (*city_notes.get(city, ()), *generic)


def _score_hit(hit: KnowledgeHit, context: TravelPlanningContext) -> float:
    text = f"{hit.title} {hit.summary}".lower()
    score = hit.score
    for term in (*context.interest_terms, *context.preference_terms, *context.style_tags):
        if term.lower() in text:
            score += 0.2
    return score


def _dedupe_hits(hits: list[KnowledgeHit]) -> list[KnowledgeHit]:
    deduped: list[KnowledgeHit] = []
    seen: set[str] = set()
    for hit in hits:
        key = f"{hit.record_type}:{hit.title.lower()}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def _record_to_view(record: object) -> KnowledgeRecordView:
    expires_at = getattr(record, "expires_at", None)
    return KnowledgeRecordView(
        id=str(getattr(record, "id")),
        destination=str(getattr(record, "destination")),
        record_type=str(getattr(record, "record_type")),
        title=str(getattr(record, "title")),
        summary=str(getattr(record, "summary")),
        source=str(getattr(record, "source")),
        score=float(getattr(record, "score")),
        expires_at=expires_at.isoformat() if expires_at else None,
    )


def _plan_summary(plan: TripPlanResponse) -> str:
    day_themes = "; ".join(f"D{day.day}: {day.theme}" for day in plan.days[:8])
    tips = "; ".join(plan.tips[:3])
    return f"{plan.summary[:700]} Themes: {day_themes}. Tips: {tips}"[:1600]

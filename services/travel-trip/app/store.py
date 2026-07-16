from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import TripPlanRecord, TripPlanVersionRecord
from app.schemas import (
    Budget,
    SavedTripPlan,
    TripPlanListResponse,
    TripPlanResponse,
    TripPlanUpdateRequest,
    TripPlanVersion,
    TripPlanVersionListResponse,
)


class TripPlanNotFoundError(Exception):
    pass


class TripPlanVersionConflictError(Exception):
    pass


class TripPlanVersionNotFoundError(Exception):
    pass


class TripPlanStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(
        self,
        user_id: str,
        page: int,
        page_size: int,
        favorite_only: bool = False,
        query: str = "",
    ) -> TripPlanListResponse:
        with session_scope(self._session_factory) as session:
            where_clauses = [TripPlanRecord.user_id == user_id]
            if favorite_only:
                where_clauses.append(TripPlanRecord.is_favorite.is_(True))

            normalized_query = query.strip()
            if normalized_query:
                query_pattern = f"%{normalized_query}%"
                where_clauses.append(
                    or_(
                        TripPlanRecord.title.ilike(query_pattern),
                        TripPlanRecord.destination.ilike(query_pattern),
                        TripPlanRecord.interests.ilike(query_pattern),
                    )
                )

            total_items = session.scalar(select(func.count()).select_from(TripPlanRecord).where(*where_clauses))
            records = session.scalars(
                select(TripPlanRecord)
                .where(*where_clauses)
                .order_by(TripPlanRecord.is_favorite.desc(), TripPlanRecord.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            total = int(total_items or 0)
            return TripPlanListResponse(
                data=[_to_trip_plan(record) for record in records],
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=ceil(total / page_size) if total else 0,
            )

    def get(self, user_id: str, trip_plan_id: str) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record is None:
                raise TripPlanNotFoundError(trip_plan_id)
            return _to_trip_plan(record)

    def update(
        self,
        user_id: str,
        trip_plan_id: str,
        request: TripPlanUpdateRequest,
        source: str = "manual_edit",
    ) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record is None:
                raise TripPlanNotFoundError(trip_plan_id)

            if request.plan is not None:
                if request.expected_version != record.version:
                    raise TripPlanVersionConflictError(trip_plan_id)
                _save_trip_plan_version_record(session, record, source)
                canonical_plan = _canonicalize_trip_plan(
                    request.plan,
                    saved_trip_plan_id=record.id,
                    conversation_id=record.conversation_id,
                )
                values = {
                    "title": canonical_plan.title.strip(),
                    "days": len(canonical_plan.days),
                    "plan": canonical_plan.model_dump(mode="json", by_alias=True),
                    "version": TripPlanRecord.version + 1,
                    "updated_at": _now(),
                }
                if request.favorite is not None:
                    values["is_favorite"] = request.favorite
                result = session.execute(
                    update(TripPlanRecord)
                    .where(
                        TripPlanRecord.id == trip_plan_id,
                        TripPlanRecord.user_id == user_id,
                        TripPlanRecord.version == request.expected_version,
                    )
                    .values(**values)
                )
                if result.rowcount == 0:
                    raise TripPlanVersionConflictError(trip_plan_id)
                session.refresh(record)
            elif request.favorite is not None:
                record.is_favorite = request.favorite
            session.flush()
            return _to_trip_plan(record)

    def list_versions(self, user_id: str, trip_plan_id: str, page: int, page_size: int) -> TripPlanVersionListResponse:
        with session_scope(self._session_factory) as session:
            record_id = session.scalar(
                select(TripPlanRecord.id).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record_id is None:
                raise TripPlanNotFoundError(trip_plan_id)
            where_clauses = [
                TripPlanVersionRecord.user_id == user_id,
                TripPlanVersionRecord.trip_plan_id == trip_plan_id,
            ]
            total_items = session.scalar(select(func.count()).select_from(TripPlanVersionRecord).where(*where_clauses))
            records = session.scalars(
                select(TripPlanVersionRecord)
                .where(*where_clauses)
                .order_by(TripPlanVersionRecord.version.desc(), TripPlanVersionRecord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            total = int(total_items or 0)
            return TripPlanVersionListResponse(
                data=[_to_trip_plan_version(record) for record in records],
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=ceil(total / page_size) if total else 0,
            )

    def restore_version(
        self,
        user_id: str,
        trip_plan_id: str,
        version_id: str,
        expected_version: int,
    ) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            trip_plan_record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if trip_plan_record is None:
                raise TripPlanNotFoundError(trip_plan_id)
            version_record = session.scalar(
                select(TripPlanVersionRecord).where(
                    TripPlanVersionRecord.id == version_id,
                    TripPlanVersionRecord.trip_plan_id == trip_plan_id,
                    TripPlanVersionRecord.user_id == user_id,
                )
            )
            if version_record is None:
                raise TripPlanVersionNotFoundError(version_id)
            if expected_version != trip_plan_record.version:
                raise TripPlanVersionConflictError(trip_plan_id)

            _save_trip_plan_version_record(session, trip_plan_record, "restore")
            canonical_plan = _canonicalize_trip_plan(
                TripPlanResponse.model_validate(version_record.plan),
                saved_trip_plan_id=trip_plan_record.id,
                conversation_id=trip_plan_record.conversation_id,
            )
            trip_plan_record.title = canonical_plan.title.strip()
            trip_plan_record.days = len(canonical_plan.days)
            trip_plan_record.plan = canonical_plan.model_dump(mode="json", by_alias=True)
            trip_plan_record.version += 1
            trip_plan_record.updated_at = _now()
            session.flush()
            return _to_trip_plan(trip_plan_record)

    def delete(self, user_id: str, trip_plan_id: str) -> None:
        with session_scope(self._session_factory) as session:
            session.execute(
                delete(TripPlanVersionRecord).where(
                    TripPlanVersionRecord.trip_plan_id == trip_plan_id,
                    TripPlanVersionRecord.user_id == user_id,
                )
            )
            result = session.execute(
                delete(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if result.rowcount == 0:
                raise TripPlanNotFoundError(trip_plan_id)


def _to_trip_plan(record: TripPlanRecord) -> SavedTripPlan:
    return SavedTripPlan(
        id=record.id,
        conversation_id=record.conversation_id,
        title=record.title,
        destination=record.destination,
        days=record.days,
        budget=record.budget,
        interests=record.interests,
        plan=TripPlanResponse.model_validate(record.plan),
        favorite=record.is_favorite,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at or record.created_at,
    )


def _to_trip_plan_version(record: TripPlanVersionRecord) -> TripPlanVersion:
    return TripPlanVersion(
        id=record.id,
        trip_plan_id=record.trip_plan_id,
        version=record.version,
        title=record.title,
        plan=TripPlanResponse.model_validate(record.plan),
        source=record.source,
        created_at=record.created_at,
    )


def _canonicalize_trip_plan(
    plan: TripPlanResponse,
    *,
    saved_trip_plan_id: str,
    conversation_id: str | None,
) -> TripPlanResponse:
    return plan.model_copy(
        update={
            "saved_trip_plan_id": saved_trip_plan_id,
            "conversation_id": conversation_id,
            "budget": _recalculate_budget(plan),
        }
    )


def _recalculate_budget(plan: TripPlanResponse) -> Budget | None:
    if plan.budget is None:
        return None
    total_attractions = sum(attraction.ticket_price for day in plan.days for attraction in day.attractions)
    total_hotels = sum(day.hotel.estimated_cost for day in plan.days if day.hotel is not None)
    total_meals = sum(meal.estimated_cost for day in plan.days for meal in day.meals)
    total_transportation = plan.budget.total_transportation
    return Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_meals=total_meals,
        total_transportation=total_transportation,
        total=total_attractions + total_hotels + total_meals + total_transportation,
    )


def _save_trip_plan_version_record(session: Session, record: TripPlanRecord, source: str) -> None:
    existing = session.scalar(
        select(TripPlanVersionRecord.id).where(
            TripPlanVersionRecord.trip_plan_id == record.id,
            TripPlanVersionRecord.user_id == record.user_id,
            TripPlanVersionRecord.version == record.version,
        )
    )
    if existing is not None:
        return
    session.add(
        TripPlanVersionRecord(
            id=str(uuid4()),
            user_id=record.user_id,
            trip_plan_id=record.id,
            version=record.version,
            title=record.title,
            plan=record.plan,
            source=source,
            created_at=_now(),
        )
    )


def _now() -> datetime:
    return datetime.now(UTC)

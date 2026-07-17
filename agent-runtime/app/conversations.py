from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import ConversationRecord, MessageRecord, TripPlanRecord, TripPlanVersionRecord
from app.schemas import (
    AgentMode,
    Budget,
    ChatMessage,
    Conversation,
    MessageRole,
    SavedTripPlan,
    TripPlanRequest,
    TripPlanResponse,
    TripPlanUpdateRequest,
    TripPlanVersion,
)


class ConversationNotFoundError(Exception):
    pass


class TripPlanNotFoundError(Exception):
    pass


class TripPlanVersionConflictError(Exception):
    pass


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, tuple[str, Conversation]] = {}
        self._trip_plans: dict[str, tuple[str, SavedTripPlan]] = {}
        self._trip_plan_versions: dict[str, tuple[str, TripPlanVersion]] = {}

    def get_or_create(self, user_id: str, conversation_id: str | None, mode: AgentMode | str, title: str) -> Conversation:
        if conversation_id:
            return self.get(user_id, conversation_id)

        now = _now()
        conversation = Conversation(
            id=str(uuid4()),
            mode=AgentMode(mode),
            title=title,
            created_at=now,
            updated_at=now,
            messages=[],
        )
        self._conversations[conversation.id] = (user_id, conversation)
        return conversation

    def get(self, user_id: str, conversation_id: str) -> Conversation:
        item = self._conversations.get(conversation_id)
        if item is None or item[0] != user_id:
            raise ConversationNotFoundError(conversation_id)
        return item[1]

    def append_message(self, conversation: Conversation, role: MessageRole, content: str) -> ChatMessage:
        message = ChatMessage(
            id=str(uuid4()),
            role=role,
            content=content,
            created_at=_now(),
        )
        conversation.messages.append(message)
        conversation.updated_at = message.created_at
        return message

    def save_trip_plan(
        self,
        user_id: str,
        conversation: Conversation,
        request: TripPlanRequest,
        response: TripPlanResponse,
    ) -> SavedTripPlan:
        trip_plan = SavedTripPlan(
            id=str(uuid4()),
            conversation_id=conversation.id,
            title=response.title,
            destination=request.destination,
            days=request.days,
            budget=request.budget,
            interests=request.interests,
            plan=response,
            created_at=_now(),
            updated_at=_now(),
        )
        self._trip_plans[trip_plan.id] = (user_id, trip_plan)
        return trip_plan

    def get_trip_plan(self, user_id: str, trip_plan_id: str) -> SavedTripPlan:
        item = self._trip_plans.get(trip_plan_id)
        if item is None or item[0] != user_id:
            raise TripPlanNotFoundError(trip_plan_id)
        return item[1]

    def update_trip_plan(
        self,
        user_id: str,
        trip_plan_id: str,
        request: TripPlanUpdateRequest,
        source: str = "manual_edit",
    ) -> SavedTripPlan:
        item = self._trip_plans.get(trip_plan_id)
        if item is None or item[0] != user_id:
            raise TripPlanNotFoundError(trip_plan_id)

        trip_plan = item[1]
        if request.plan is not None:
            if request.expected_version != trip_plan.version:
                raise TripPlanVersionConflictError(trip_plan_id)
            self._save_trip_plan_version(user_id, trip_plan, source)
            trip_plan.plan = _canonicalize_trip_plan(
                request.plan,
                saved_trip_plan_id=trip_plan.id,
                conversation_id=trip_plan.conversation_id,
            )
            trip_plan.title = trip_plan.plan.title.strip()
            trip_plan.days = len(trip_plan.plan.days)
            trip_plan.version += 1
            trip_plan.updated_at = _now()
        if request.favorite is not None:
            trip_plan.favorite = request.favorite
        return trip_plan

    def _save_trip_plan_version(self, user_id: str, trip_plan: SavedTripPlan, source: str) -> None:
        version = TripPlanVersion(
            id=str(uuid4()),
            trip_plan_id=trip_plan.id,
            version=trip_plan.version,
            title=trip_plan.title,
            plan=trip_plan.plan,
            source=source,
            created_at=_now(),
        )
        self._trip_plan_versions[version.id] = (user_id, version)


class DatabaseConversationStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_or_create(self, user_id: str, conversation_id: str | None, mode: AgentMode | str, title: str) -> Conversation:
        with session_scope(self._session_factory) as session:
            if conversation_id:
                record = _get_conversation_record(session, user_id, conversation_id)
                if record is None:
                    raise ConversationNotFoundError(conversation_id)
                return _to_conversation(record)

            record = ConversationRecord(user_id=user_id, mode=AgentMode(mode).value, title=title)
            session.add(record)
            session.flush()
            return _to_conversation(record)

    def get(self, user_id: str, conversation_id: str) -> Conversation:
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(conversation_id)
            return _to_conversation(record)

    def append_message(self, conversation: Conversation, role: MessageRole, content: str) -> ChatMessage:
        created_at = _now()
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id=None, conversation_id=conversation.id)
            if record is None:
                raise ConversationNotFoundError(conversation.id)

            message_record = MessageRecord(
                conversation_id=conversation.id,
                role=role.value,
                content=content,
                created_at=created_at,
            )
            record.updated_at = created_at
            session.add(message_record)
            session.flush()

            message = _to_message(message_record)
            conversation.messages.append(message)
            conversation.updated_at = created_at
            return message

    def save_trip_plan(
        self,
        user_id: str,
        conversation: Conversation,
        request: TripPlanRequest,
        response: TripPlanResponse,
    ) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = TripPlanRecord(
                user_id=user_id,
                conversation_id=conversation.id,
                title=response.title,
                destination=request.destination,
                days=request.days,
                budget=request.budget,
                interests=request.interests,
                plan=response.model_dump(mode="json", by_alias=True),
            )
            session.add(record)
            session.flush()
            return _to_trip_plan(record)

    def get_trip_plan(self, user_id: str, trip_plan_id: str) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record is None:
                raise TripPlanNotFoundError(trip_plan_id)
            return _to_trip_plan(record)

    def update_trip_plan(
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

    total_attractions = sum(
        attraction.ticket_price for day in plan.days for attraction in (day.attractions or [])
    )
    total_hotels = sum(day.hotel.estimated_cost for day in plan.days if day.hotel is not None)
    total_meals = sum(meal.estimated_cost for day in plan.days for meal in (day.meals or []))
    total_transportation = plan.budget.total_transportation
    return Budget(
        total_attractions=total_attractions,
        total_hotels=total_hotels,
        total_meals=total_meals,
        total_transportation=total_transportation,
        total=total_attractions + total_hotels + total_meals + total_transportation,
    )


def _get_conversation_record(
    session: Session,
    user_id: str | None,
    conversation_id: str,
) -> ConversationRecord | None:
    statement = select(ConversationRecord).where(ConversationRecord.id == conversation_id)
    if user_id is not None:
        statement = statement.where(ConversationRecord.user_id == user_id)
    return session.scalar(statement)


def _to_conversation(record: ConversationRecord) -> Conversation:
    return Conversation(
        id=record.id,
        mode=AgentMode(record.mode),
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
        messages=[_to_message(message) for message in record.messages],
    )


def _to_message(record: MessageRecord) -> ChatMessage:
    return ChatMessage(
        id=record.id,
        role=MessageRole(record.role),
        content=record.content,
        created_at=record.created_at,
    )


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

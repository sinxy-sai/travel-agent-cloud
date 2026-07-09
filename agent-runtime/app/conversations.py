from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import ConversationRecord, MessageRecord, TripPlanRecord
from app.schemas import (
    AgentMode,
    ChatMessage,
    Conversation,
    ConversationListResponse,
    MessageRole,
    SavedTripPlan,
    TripPlanListResponse,
    TripPlanRequest,
    TripPlanResponse,
)


class ConversationNotFoundError(Exception):
    pass


class TripPlanNotFoundError(Exception):
    pass


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, tuple[str, Conversation]] = {}
        self._trip_plans: dict[str, tuple[str, SavedTripPlan]] = {}

    def get_or_create(self, user_id: str, conversation_id: str | None, mode: AgentMode | str, title: str) -> Conversation:
        if conversation_id:
            item = self._conversations.get(conversation_id)
            if item is None or item[0] != user_id:
                raise ConversationNotFoundError(conversation_id)
            return item[1]

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

    def delete(self, user_id: str, conversation_id: str) -> None:
        item = self._conversations.get(conversation_id)
        if item is None or item[0] != user_id:
            raise ConversationNotFoundError(conversation_id)

        del self._conversations[conversation_id]
        for owner_id, trip_plan in self._trip_plans.values():
            if owner_id == user_id and trip_plan.conversation_id == conversation_id:
                trip_plan.conversation_id = None

    def list(self, user_id: str, page: int, page_size: int) -> ConversationListResponse:
        conversations = sorted(
            [conversation for owner_id, conversation in self._conversations.values() if owner_id == user_id],
            key=lambda conversation: conversation.updated_at,
            reverse=True,
        )
        start = (page - 1) * page_size
        end = start + page_size
        total_items = len(conversations)
        return ConversationListResponse(
            data=conversations[start:end],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=ceil(total_items / page_size) if total_items else 0,
        )

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
        )
        self._trip_plans[trip_plan.id] = (user_id, trip_plan)
        return trip_plan

    def list_trip_plans(
        self,
        user_id: str,
        page: int,
        page_size: int,
        favorite_only: bool = False,
        query: str = "",
    ) -> TripPlanListResponse:
        normalized_query = query.strip().lower()
        trip_plans = sorted(
            [
                trip_plan
                for owner_id, trip_plan in self._trip_plans.values()
                if owner_id == user_id
                and (not favorite_only or trip_plan.favorite)
                and _matches_trip_plan_query(trip_plan, normalized_query)
            ],
            key=lambda trip_plan: (trip_plan.favorite, trip_plan.created_at),
            reverse=True,
        )
        start = (page - 1) * page_size
        end = start + page_size
        total_items = len(trip_plans)
        return TripPlanListResponse(
            data=trip_plans[start:end],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=ceil(total_items / page_size) if total_items else 0,
        )

    def get_trip_plan(self, user_id: str, trip_plan_id: str) -> SavedTripPlan:
        item = self._trip_plans.get(trip_plan_id)
        if item is None or item[0] != user_id:
            raise TripPlanNotFoundError(trip_plan_id)
        return item[1]

    def delete_trip_plan(self, user_id: str, trip_plan_id: str) -> None:
        item = self._trip_plans.get(trip_plan_id)
        if item is None or item[0] != user_id:
            raise TripPlanNotFoundError(trip_plan_id)
        del self._trip_plans[trip_plan_id]

    def update_trip_plan_favorite(self, user_id: str, trip_plan_id: str, favorite: bool) -> SavedTripPlan:
        item = self._trip_plans.get(trip_plan_id)
        if item is None or item[0] != user_id:
            raise TripPlanNotFoundError(trip_plan_id)
        item[1].favorite = favorite
        return item[1]


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

    def delete(self, user_id: str, conversation_id: str) -> None:
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(conversation_id)
            session.execute(
                update(TripPlanRecord)
                .where(TripPlanRecord.conversation_id == conversation_id, TripPlanRecord.user_id == user_id)
                .values(conversation_id=None)
            )
            session.execute(
                delete(MessageRecord).where(MessageRecord.conversation_id == conversation_id)
            )
            session.execute(
                delete(ConversationRecord).where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.user_id == user_id,
                )
            )

    def list(self, user_id: str, page: int, page_size: int) -> ConversationListResponse:
        with session_scope(self._session_factory) as session:
            total_items = session.scalar(
                select(func.count()).select_from(ConversationRecord).where(ConversationRecord.user_id == user_id)
            )
            records = session.scalars(
                select(ConversationRecord)
                .where(ConversationRecord.user_id == user_id)
                .order_by(ConversationRecord.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()

            total = int(total_items or 0)
            return ConversationListResponse(
                data=[_to_conversation(record) for record in records],
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=ceil(total / page_size) if total else 0,
            )

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

    def list_trip_plans(
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
                .order_by(TripPlanRecord.is_favorite.desc(), TripPlanRecord.created_at.desc())
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

    def get_trip_plan(self, user_id: str, trip_plan_id: str) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record is None:
                raise TripPlanNotFoundError(trip_plan_id)
            return _to_trip_plan(record)

    def delete_trip_plan(self, user_id: str, trip_plan_id: str) -> None:
        with session_scope(self._session_factory) as session:
            result = session.execute(
                delete(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if result.rowcount == 0:
                raise TripPlanNotFoundError(trip_plan_id)

    def update_trip_plan_favorite(self, user_id: str, trip_plan_id: str, favorite: bool) -> SavedTripPlan:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(TripPlanRecord).where(TripPlanRecord.id == trip_plan_id, TripPlanRecord.user_id == user_id)
            )
            if record is None:
                raise TripPlanNotFoundError(trip_plan_id)

            record.is_favorite = favorite
            session.flush()
            return _to_trip_plan(record)


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
        created_at=record.created_at,
    )


def _matches_trip_plan_query(trip_plan: SavedTripPlan, normalized_query: str) -> bool:
    if not normalized_query:
        return True
    searchable_text = " ".join([trip_plan.title, trip_plan.destination, trip_plan.interests]).lower()
    return normalized_query in searchable_text


def _now() -> datetime:
    return datetime.now(UTC)

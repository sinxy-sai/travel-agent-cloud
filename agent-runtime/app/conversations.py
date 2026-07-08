from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import ConversationRecord, MessageRecord, TripPlanRecord
from app.schemas import (
    AgentMode,
    ChatMessage,
    Conversation,
    ConversationListResponse,
    MessageRole,
    TripPlanRequest,
    TripPlanResponse,
)


class ConversationNotFoundError(Exception):
    pass


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, tuple[str, Conversation]] = {}

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
    ) -> None:
        return None


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
    ) -> None:
        with session_scope(self._session_factory) as session:
            session.add(
                TripPlanRecord(
                    user_id=user_id,
                    conversation_id=conversation.id,
                    title=response.title,
                    destination=request.destination,
                    days=request.days,
                    budget=request.budget,
                    interests=request.interests,
                    plan=response.model_dump(mode="json", by_alias=True),
                )
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


def _now() -> datetime:
    return datetime.now(UTC)

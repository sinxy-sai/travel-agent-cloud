from datetime import UTC, datetime
from math import ceil

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.db import session_scope
from app.models import ConversationRecord, ConversationSummaryRecord, MessageRecord
from app.schemas import (
    AgentMode,
    ChatMessage,
    Conversation,
    ConversationListResponse,
    ConversationSummary,
    MessageRole,
)


class ConversationNotFoundError(Exception):
    pass


class ConversationSummaryNotFoundError(Exception):
    pass


class ConversationStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(self, user_id: str, page: int, page_size: int, query: str = "") -> ConversationListResponse:
        with session_scope(self._session_factory) as session:
            where_clauses = [ConversationRecord.user_id == user_id]
            normalized_query = query.strip()
            if normalized_query:
                query_pattern = f"%{normalized_query}%"
                matching_message_conversation_ids = select(MessageRecord.conversation_id).where(
                    MessageRecord.content.ilike(query_pattern)
                )
                where_clauses.append(
                    or_(
                        ConversationRecord.title.ilike(query_pattern),
                        ConversationRecord.id.in_(matching_message_conversation_ids),
                    )
                )
            total_items = int(
                session.scalar(select(func.count()).select_from(ConversationRecord).where(*where_clauses)) or 0
            )
            records = session.scalars(
                select(ConversationRecord)
                .where(*where_clauses)
                .order_by(ConversationRecord.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return ConversationListResponse(
                data=[_to_conversation(record) for record in records],
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=ceil(total_items / page_size) if total_items else 0,
            )

    def get(self, user_id: str, conversation_id: str) -> Conversation:
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(conversation_id)
            return _to_conversation(record)

    def update_title(self, user_id: str, conversation_id: str, title: str) -> Conversation:
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(conversation_id)
            record.title = title.strip()
            record.updated_at = _now()
            session.flush()
            return _to_conversation(record)

    def delete(self, user_id: str, conversation_id: str) -> None:
        with session_scope(self._session_factory) as session:
            record = _get_conversation_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationNotFoundError(conversation_id)
            _clear_trip_plan_conversation_links(session, user_id, conversation_id)
            session.execute(
                delete(ConversationSummaryRecord).where(
                    ConversationSummaryRecord.conversation_id == conversation_id,
                    ConversationSummaryRecord.user_id == user_id,
                )
            )
            session.execute(delete(MessageRecord).where(MessageRecord.conversation_id == conversation_id))
            session.execute(
                delete(ConversationRecord).where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.user_id == user_id,
                )
            )


class ConversationSummaryStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, user_id: str, conversation_id: str) -> ConversationSummary:
        with session_scope(self._session_factory) as session:
            record = _get_summary_record(session, user_id, conversation_id)
            if record is None:
                raise ConversationSummaryNotFoundError(conversation_id)
            return _to_summary(record)

    def save(self, user_id: str, conversation_id: str, summary: str, message_count: int) -> ConversationSummary:
        with session_scope(self._session_factory) as session:
            conversation = _get_conversation_record(session, user_id, conversation_id)
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)
            record = _get_summary_record(session, user_id, conversation_id)
            now = _now()
            if record is None:
                record = ConversationSummaryRecord(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    summary=summary,
                    message_count=message_count,
                )
                session.add(record)
            else:
                record.summary = summary
                record.message_count = message_count
                record.updated_at = now
            session.flush()
            return _to_summary(record)


def build_conversation_summary(messages: list[ChatMessage]) -> str:
    if not messages:
        return "No messages have been added to this conversation yet."
    user_messages = [message.content.strip() for message in messages if message.role == MessageRole.USER]
    assistant_messages = [message.content.strip() for message in messages if message.role == MessageRole.ASSISTANT]
    latest_messages = [message.content.strip() for message in messages[-4:]]
    lines = [f"Conversation contains {len(messages)} messages."]
    if user_messages:
        lines.append(f"Latest user request: {_compact(user_messages[-1])}")
    if assistant_messages:
        lines.append(f"Latest assistant answer: {_compact(assistant_messages[-1])}")
    if latest_messages:
        lines.append("Recent context:")
        lines.extend(f"- {_compact(content, max_length=180)}" for content in latest_messages if content)
    return "\n".join(lines)


def _clear_trip_plan_conversation_links(session: Session, user_id: str, conversation_id: str) -> None:
    try:
        session.execute(
            text(
                """
                UPDATE trip_plans
                SET conversation_id = NULL, updated_at = :updated_at
                WHERE conversation_id = :conversation_id AND user_id = :user_id
                """
            ),
            {"conversation_id": conversation_id, "user_id": user_id, "updated_at": _now()},
        )
    except (OperationalError, ProgrammingError):
        # Standalone travel-agent dev databases may not have travel-trip tables yet.
        session.rollback()


def _get_conversation_record(session: Session, user_id: str, conversation_id: str) -> ConversationRecord | None:
    return session.scalar(
        select(ConversationRecord).where(
            ConversationRecord.id == conversation_id,
            ConversationRecord.user_id == user_id,
        )
    )


def _get_summary_record(session: Session, user_id: str, conversation_id: str) -> ConversationSummaryRecord | None:
    return session.scalar(
        select(ConversationSummaryRecord).where(
            ConversationSummaryRecord.conversation_id == conversation_id,
            ConversationSummaryRecord.user_id == user_id,
        )
    )


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


def _to_summary(record: ConversationSummaryRecord) -> ConversationSummary:
    return ConversationSummary(
        id=record.id,
        conversation_id=record.conversation_id,
        summary=record.summary,
        message_count=record.message_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _compact(value: str, max_length: int = 240) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= max_length else normalized[: max_length - 3].rstrip() + "..."


def _now() -> datetime:
    return datetime.now(UTC)

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.conversations import ConversationNotFoundError
from app.db import session_scope
from app.models import ConversationRecord, ConversationSummaryRecord
from app.schemas import ChatMessage, ConversationSummary, MessageRole


class ConversationSummaryNotFoundError(Exception):
    pass


class ConversationSummaryStore:
    def __init__(self) -> None:
        self._summaries: dict[str, tuple[str, ConversationSummary]] = {}

    def get(self, user_id: str, conversation_id: str) -> ConversationSummary:
        item = self._summaries.get(conversation_id)
        if item is None or item[0] != user_id:
            raise ConversationSummaryNotFoundError(conversation_id)
        return item[1]

    def save(self, user_id: str, conversation_id: str, summary: str, message_count: int) -> ConversationSummary:
        now = _now()
        existing = self._summaries.get(conversation_id)
        if existing is None or existing[0] != user_id:
            item = ConversationSummary(
                id=str(uuid4()),
                conversation_id=conversation_id,
                summary=summary,
                message_count=message_count,
                created_at=now,
                updated_at=now,
            )
        else:
            item = existing[1]
            item.summary = summary
            item.message_count = message_count
            item.updated_at = now
        self._summaries[conversation_id] = (user_id, item)
        return item

    def delete_for_conversation(self, user_id: str, conversation_id: str) -> None:
        item = self._summaries.get(conversation_id)
        if item is not None and item[0] == user_id:
            del self._summaries[conversation_id]


class DatabaseConversationSummaryStore:
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
            conversation = session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.user_id == user_id,
                )
            )
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

    def delete_for_conversation(self, user_id: str, conversation_id: str) -> None:
        with session_scope(self._session_factory) as session:
            session.execute(
                delete(ConversationSummaryRecord).where(
                    ConversationSummaryRecord.conversation_id == conversation_id,
                    ConversationSummaryRecord.user_id == user_id,
                )
            )


def build_conversation_summary(messages: list[ChatMessage]) -> str:
    if not messages:
        return "No messages have been added to this conversation yet."

    user_messages = [message.content.strip() for message in messages if message.role == MessageRole.USER]
    assistant_messages = [message.content.strip() for message in messages if message.role == MessageRole.ASSISTANT]
    latest_messages = [message.content.strip() for message in messages[-4:]]

    lines = [
        f"Conversation contains {len(messages)} messages.",
    ]
    if user_messages:
        lines.append(f"Latest user request: {_compact(user_messages[-1])}")
    if assistant_messages:
        lines.append(f"Latest assistant answer: {_compact(assistant_messages[-1])}")
    if latest_messages:
        lines.append("Recent context:")
        lines.extend(f"- {_compact(content, max_length=180)}" for content in latest_messages if content)

    return "\n".join(lines)


def _get_summary_record(
    session: Session,
    user_id: str,
    conversation_id: str,
) -> ConversationSummaryRecord | None:
    return session.scalar(
        select(ConversationSummaryRecord).where(
            ConversationSummaryRecord.conversation_id == conversation_id,
            ConversationSummaryRecord.user_id == user_id,
        )
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

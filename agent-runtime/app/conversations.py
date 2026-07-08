from datetime import UTC, datetime
from math import ceil
from uuid import uuid4

from app.schemas import (
    AgentMode,
    ChatMessage,
    Conversation,
    ConversationListResponse,
    MessageRole,
)


class ConversationNotFoundError(Exception):
    pass


class ConversationStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def get_or_create(self, conversation_id: str | None, mode: AgentMode, title: str) -> Conversation:
        if conversation_id:
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                raise ConversationNotFoundError(conversation_id)
            return conversation

        now = _now()
        conversation = Conversation(
            id=str(uuid4()),
            mode=mode,
            title=title,
            created_at=now,
            updated_at=now,
            messages=[],
        )
        self._conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    def list(self, page: int, page_size: int) -> ConversationListResponse:
        conversations = sorted(
            self._conversations.values(),
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


def _now() -> datetime:
    return datetime.now(UTC)

from dataclasses import dataclass
from typing import Protocol

from app.events import (
    CONVERSATION_SUMMARY_CREATED_EVENT,
    CONVERSATION_SUMMARY_REQUESTED_EVENT,
    EventPublisher,
)
from app.schemas import Conversation, ConversationSummary
from app.summaries import build_conversation_summary


class ConversationReader(Protocol):
    def get(self, user_id: str, conversation_id: str) -> Conversation:
        pass


class ConversationSummaryWriter(Protocol):
    def save(self, user_id: str, conversation_id: str, summary: str, message_count: int) -> ConversationSummary:
        pass


@dataclass(frozen=True)
class SummarizeConversationCommand:
    user_id: str
    conversation_id: str
    requested_by: str = "manual_api"
    emit_requested_event: bool = True


class ConversationSummarizerWorker:
    """Synchronous worker core that can later be called by a RabbitMQ consumer."""

    def __init__(
        self,
        conversation_store: ConversationReader,
        summary_store: ConversationSummaryWriter,
        event_publisher: EventPublisher,
    ) -> None:
        self._conversation_store = conversation_store
        self._summary_store = summary_store
        self._event_publisher = event_publisher

    def handle(self, command: SummarizeConversationCommand) -> ConversationSummary:
        conversation = self._conversation_store.get(command.user_id, command.conversation_id)
        if command.emit_requested_event:
            self._event_publisher.publish(
                CONVERSATION_SUMMARY_REQUESTED_EVENT,
                command.user_id,
                {
                    "conversationId": command.conversation_id,
                    "requestedBy": command.requested_by,
                    "messageCount": len(conversation.messages),
                },
            )

        summary = self._summary_store.save(
            user_id=command.user_id,
            conversation_id=command.conversation_id,
            summary=build_conversation_summary(conversation.messages),
            message_count=len(conversation.messages),
        )

        self._event_publisher.publish(
            CONVERSATION_SUMMARY_CREATED_EVENT,
            command.user_id,
            {
                "conversationId": command.conversation_id,
                "summaryId": summary.id,
                "messageCount": summary.message_count,
                "requestedBy": command.requested_by,
            },
        )
        return summary

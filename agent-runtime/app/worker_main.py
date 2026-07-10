import logging
import sys

from app.conversations import DatabaseConversationStore
from app.db import maybe_create_session_factory
from app.events import create_event_publisher
from app.observability import configure_logging
from app.settings import get_settings
from app.summaries import DatabaseConversationSummaryStore
from app.workers.conversation_summarizer import ConversationSummarizerWorker
from app.workers.rabbitmq_consumer import RabbitMQConsumerConfig, RabbitMQConversationSummaryConsumer

logger = logging.getLogger("travel_agent_runtime.worker")


def main() -> int:
    settings = get_settings()
    configure_logging(settings)

    if not settings.message_queue_url:
        logger.error("worker_start_failed reason=missing_message_queue_url")
        return 2
    if not settings.database_url:
        logger.error("worker_start_failed reason=missing_database_url")
        return 2

    session_factory = maybe_create_session_factory(settings)
    if session_factory is None:
        logger.error("worker_start_failed reason=database_unavailable")
        return 2

    conversation_store = DatabaseConversationStore(session_factory)
    summary_store = DatabaseConversationSummaryStore(session_factory)

    summarizer = ConversationSummarizerWorker(
        conversation_store=conversation_store,
        summary_store=summary_store,
        event_publisher=create_event_publisher(settings),
    )
    consumer = RabbitMQConversationSummaryConsumer(
        config=RabbitMQConsumerConfig(
            message_queue_url=settings.message_queue_url,
            timeout_seconds=settings.rpc_timeout_seconds,
        ),
        worker=summarizer,
    )
    consumer.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

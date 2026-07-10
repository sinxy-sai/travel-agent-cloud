import logging
import sys
import time

from app.conversations import DatabaseConversationStore
from app.db import maybe_create_session_factory
from app.events import create_event_publisher
from app.observability import configure_logging
from app.settings import Settings, get_settings
from app.summaries import DatabaseConversationSummaryStore
from app.summary_jobs import DatabaseConversationSummaryJobStore
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

    initial_reconnect_delay = max(settings.worker_reconnect_initial_seconds, 0.1)
    max_reconnect_delay = max(settings.worker_reconnect_max_seconds, initial_reconnect_delay)
    reconnect_delay = initial_reconnect_delay

    while True:
        try:
            _start_consumer(settings)
            reconnect_delay = initial_reconnect_delay
        except KeyboardInterrupt:
            logger.info("worker_stopped reason=keyboard_interrupt")
            return 0
        except Exception as exc:
            logger.warning(
                "worker_connection_failed error=%s retry_in_seconds=%.1f",
                exc.__class__.__name__,
                reconnect_delay,
            )
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


def _start_consumer(settings: Settings) -> None:
    session_factory = maybe_create_session_factory(settings)
    if session_factory is None:
        raise RuntimeError("database_unavailable")

    conversation_store = DatabaseConversationStore(session_factory)
    summary_store = DatabaseConversationSummaryStore(session_factory)
    summary_job_store = DatabaseConversationSummaryJobStore(session_factory)

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
        job_tracker=summary_job_store,
    )
    consumer.start()


if __name__ == "__main__":
    sys.exit(main())

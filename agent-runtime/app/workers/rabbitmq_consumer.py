import json
import logging
from dataclasses import dataclass
from typing import Any

from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, EVENT_EXCHANGE
from app.workers.conversation_summarizer import ConversationSummarizerWorker, SummarizeConversationCommand

logger = logging.getLogger("travel_agent_runtime.worker")

CONVERSATION_SUMMARIZER_QUEUE = "travel.conversation_summarizer"
DEAD_LETTER_EXCHANGE = "travel.events.dlx"
DEAD_LETTER_QUEUE = "travel.conversation_summarizer.dlq"


class EventPayloadError(Exception):
    pass


@dataclass(frozen=True)
class RabbitMQConsumerConfig:
    message_queue_url: str
    timeout_seconds: float
    prefetch_count: int = 1


class RabbitMQConversationSummaryConsumer:
    def __init__(self, config: RabbitMQConsumerConfig, worker: ConversationSummarizerWorker) -> None:
        self._config = config
        self._worker = worker

    def start(self) -> None:
        import pika

        parameters = pika.URLParameters(self._config.message_queue_url)
        parameters.socket_timeout = self._config.timeout_seconds
        parameters.blocked_connection_timeout = self._config.timeout_seconds
        parameters.heartbeat = 30

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        _declare_topology(channel)
        channel.basic_qos(prefetch_count=self._config.prefetch_count)
        channel.basic_consume(
            queue=CONVERSATION_SUMMARIZER_QUEUE,
            on_message_callback=self._handle_message,
            auto_ack=False,
        )
        logger.info("conversation_summarizer_consumer_started queue=%s", CONVERSATION_SUMMARIZER_QUEUE)
        try:
            channel.start_consuming()
        finally:
            connection.close()

    def _handle_message(self, channel: Any, method: Any, properties: Any, body: bytes) -> None:
        event_id = _property_header(properties, "eventId") or "unknown"
        try:
            command = _parse_summary_command(body)
            if command.requested_by == "manual_api":
                channel.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(
                    "conversation_summary_job_skipped event_id=%s conversation_id=%s reason=manual_api_already_processed",
                    event_id,
                    command.conversation_id,
                )
                return

            summary = self._worker.handle(command)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(
                "conversation_summary_job_completed event_id=%s conversation_id=%s summary_id=%s",
                event_id,
                command.conversation_id,
                summary.id,
            )
        except EventPayloadError as exc:
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            logger.warning("conversation_summary_job_rejected event_id=%s error=%s", event_id, exc)
        except Exception as exc:
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            logger.exception("conversation_summary_job_failed event_id=%s error=%s", event_id, exc.__class__.__name__)


def _declare_topology(channel: Any) -> None:
    channel.exchange_declare(exchange=EVENT_EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DEAD_LETTER_EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue=DEAD_LETTER_QUEUE, durable=True)
    channel.queue_bind(
        queue=DEAD_LETTER_QUEUE,
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key="#",
    )
    channel.queue_declare(
        queue=CONVERSATION_SUMMARIZER_QUEUE,
        durable=True,
        arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE},
    )
    channel.queue_bind(
        queue=CONVERSATION_SUMMARIZER_QUEUE,
        exchange=EVENT_EXCHANGE,
        routing_key=CONVERSATION_SUMMARY_REQUESTED_EVENT,
    )


def _parse_summary_command(body: bytes) -> SummarizeConversationCommand:
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventPayloadError("Invalid JSON event payload") from exc

    event_type = event.get("eventType")
    if event_type != CONVERSATION_SUMMARY_REQUESTED_EVENT:
        raise EventPayloadError(f"Unsupported event type: {event_type}")

    data = event.get("data") if isinstance(event.get("data"), dict) else event
    user_id = _required_text(event, "userId")
    conversation_id = _required_text(data, "conversationId")
    requested_by = data.get("requestedBy") if isinstance(data.get("requestedBy"), str) else "rabbitmq"

    return SummarizeConversationCommand(
        user_id=user_id,
        conversation_id=conversation_id,
        requested_by=requested_by,
        emit_requested_event=False,
    )


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EventPayloadError(f"Missing required field: {field}")
    return value


def _property_header(properties: Any, name: str) -> str | None:
    headers = getattr(properties, "headers", None)
    if not isinstance(headers, dict):
        return None
    value = headers.get(name)
    return value if isinstance(value, str) else None

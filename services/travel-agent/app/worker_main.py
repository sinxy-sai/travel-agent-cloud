import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from app.db import create_session_factory
from app.events import CONVERSATION_SUMMARY_REQUESTED_EVENT, EVENT_EXCHANGE
from app.store import (
    ConversationNotFoundError,
    ConversationStore,
    ConversationSummaryJobNotFoundError,
    ConversationSummaryJobStore,
    ConversationSummaryStore,
    build_conversation_summary,
)


logger = logging.getLogger("travel_agent.worker")
CONVERSATION_SUMMARIZER_QUEUE = "travel.conversation_summarizer"
DEAD_LETTER_EXCHANGE = "travel.events.dlx"
DEAD_LETTER_QUEUE = "travel.conversation_summarizer.dlq"


class EventPayloadError(Exception):
    pass


@dataclass(frozen=True)
class SummaryCommand:
    user_id: str
    conversation_id: str
    summary_job_id: str | None
    requested_by: str


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    database_url = os.getenv("DATABASE_URL", "").strip()
    message_queue_url = os.getenv("MESSAGE_QUEUE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for travel-agent-worker")
    if not message_queue_url:
        raise RuntimeError("MESSAGE_QUEUE_URL is required for travel-agent-worker")

    session_factory = create_session_factory(database_url)
    conversation_store = ConversationStore(session_factory)
    summary_store = ConversationSummaryStore(session_factory)
    job_store = ConversationSummaryJobStore(session_factory)
    timeout_seconds = float(os.getenv("RPC_TIMEOUT_SECONDS", "5"))

    reconnect_initial = float(os.getenv("WORKER_RECONNECT_INITIAL_SECONDS", "2"))
    reconnect_max = float(os.getenv("WORKER_RECONNECT_MAX_SECONDS", "30"))
    delay = reconnect_initial
    while True:
        try:
            _consume(message_queue_url, timeout_seconds, conversation_store, summary_store, job_store)
            delay = reconnect_initial
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.warning("travel_agent_worker_reconnecting error=%s delay=%s", exc.__class__.__name__, delay)
            time.sleep(delay)
            delay = min(delay * 2, reconnect_max)


def _consume(
    message_queue_url: str,
    timeout_seconds: float,
    conversation_store: ConversationStore,
    summary_store: ConversationSummaryStore,
    job_store: ConversationSummaryJobStore,
) -> None:
    import pika

    parameters = pika.URLParameters(message_queue_url)
    parameters.socket_timeout = timeout_seconds
    parameters.blocked_connection_timeout = timeout_seconds
    parameters.heartbeat = 30
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    _declare_topology(channel)
    channel.basic_qos(prefetch_count=1)

    def handle_message(channel: Any, method: Any, properties: Any, body: bytes) -> None:
        try:
            command = _parse_summary_command(body)
            if command.summary_job_id:
                _mark_job_running(job_store, command)
            conversation = conversation_store.get(command.user_id, command.conversation_id)
            summary = build_conversation_summary(conversation.messages)
            summary_store.save(command.user_id, command.conversation_id, summary, len(conversation.messages))
            if command.summary_job_id:
                _mark_job_succeeded(job_store, command)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except EventPayloadError as exc:
            logger.warning("conversation_summary_job_rejected error=%s", exc)
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as exc:
            if "command" in locals() and command.summary_job_id:
                _mark_job_failed(job_store, command, str(exc) or exc.__class__.__name__)
            logger.exception("conversation_summary_job_failed error=%s", exc.__class__.__name__)
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue=CONVERSATION_SUMMARIZER_QUEUE, on_message_callback=handle_message, auto_ack=False)
    logger.info("travel_agent_worker_started queue=%s", CONVERSATION_SUMMARIZER_QUEUE)
    try:
        channel.start_consuming()
    finally:
        if connection.is_open:
            connection.close()


def _declare_topology(channel: Any) -> None:
    channel.exchange_declare(exchange=EVENT_EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DEAD_LETTER_EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue=DEAD_LETTER_QUEUE, durable=True)
    channel.queue_bind(queue=DEAD_LETTER_QUEUE, exchange=DEAD_LETTER_EXCHANGE, routing_key="#")
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


def _parse_summary_command(body: bytes) -> SummaryCommand:
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventPayloadError("Invalid JSON event payload") from exc
    if event.get("eventType") != CONVERSATION_SUMMARY_REQUESTED_EVENT:
        raise EventPayloadError(f"Unsupported event type: {event.get('eventType')}")
    data = event.get("data") if isinstance(event.get("data"), dict) else event
    return SummaryCommand(
        user_id=_required_text(event, "userId"),
        conversation_id=_required_text(data, "conversationId"),
        summary_job_id=data.get("summaryJobId") if isinstance(data.get("summaryJobId"), str) else None,
        requested_by=data.get("requestedBy") if isinstance(data.get("requestedBy"), str) else "rabbitmq",
    )


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EventPayloadError(f"Missing required field: {field}")
    return value


def _mark_job_running(job_store: ConversationSummaryJobStore, command: SummaryCommand) -> None:
    try:
        job_store.mark_running(command.user_id, command.summary_job_id or "")
    except ConversationSummaryJobNotFoundError:
        logger.warning("summary_job_missing job_id=%s status=RUNNING", command.summary_job_id)


def _mark_job_succeeded(job_store: ConversationSummaryJobStore, command: SummaryCommand) -> None:
    try:
        job_store.mark_succeeded(command.user_id, command.summary_job_id or "")
    except ConversationSummaryJobNotFoundError:
        logger.warning("summary_job_missing job_id=%s status=SUCCEEDED", command.summary_job_id)


def _mark_job_failed(job_store: ConversationSummaryJobStore, command: SummaryCommand, error_message: str) -> None:
    try:
        job_store.mark_failed(command.user_id, command.summary_job_id or "", error_message)
    except ConversationSummaryJobNotFoundError:
        logger.warning("summary_job_missing job_id=%s status=FAILED", command.summary_job_id)


if __name__ == "__main__":
    main()

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from app.settings import Settings

logger = logging.getLogger("travel_agent_runtime.events")
EVENT_EXCHANGE = "travel.events"


class EventPublisher(Protocol):
    enabled: bool

    def publish(self, event_type: str, user_id: str, data: dict[str, Any]) -> None:
        pass


class NoopEventPublisher:
    enabled = False

    def publish(self, event_type: str, user_id: str, data: dict[str, Any]) -> None:
        return None


class RabbitMQEventPublisher:
    enabled = True

    def __init__(self, message_queue_url: str, timeout_seconds: float) -> None:
        self._message_queue_url = message_queue_url
        self._timeout_seconds = timeout_seconds

    def publish(self, event_type: str, user_id: str, data: dict[str, Any]) -> None:
        try:
            self._publish(event_type, user_id, data)
        except Exception as exc:
            logger.warning("event_publish_failed event_type=%s error=%s", event_type, exc.__class__.__name__)

    def _publish(self, event_type: str, user_id: str, data: dict[str, Any]) -> None:
        import pika

        event = _build_event(event_type, user_id, data)
        parameters = pika.URLParameters(self._message_queue_url)
        parameters.socket_timeout = self._timeout_seconds
        parameters.blocked_connection_timeout = self._timeout_seconds
        parameters.heartbeat = 30

        connection = pika.BlockingConnection(parameters)
        try:
            channel = connection.channel()
            channel.exchange_declare(exchange=EVENT_EXCHANGE, exchange_type="topic", durable=True)
            channel.basic_publish(
                exchange=EVENT_EXCHANGE,
                routing_key=event_type,
                body=json.dumps(event, ensure_ascii=False).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    headers={"eventType": event_type, "eventId": event["eventId"]},
                ),
            )
            logger.info("event_published event_id=%s event_type=%s", event["eventId"], event_type)
        finally:
            connection.close()


def create_event_publisher(settings: Settings) -> EventPublisher:
    if not settings.message_queue_url:
        return NoopEventPublisher()
    return RabbitMQEventPublisher(settings.message_queue_url, settings.rpc_timeout_seconds)


def _build_event(event_type: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventId": str(uuid4()),
        "eventType": event_type,
        "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "userId": user_id,
        "data": data,
    }

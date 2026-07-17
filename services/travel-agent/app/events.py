import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


logger = logging.getLogger("travel_agent_service.events")
EVENT_EXCHANGE = "travel.events"
CONVERSATION_SUMMARY_REQUESTED_EVENT = "agent.conversation.summarize.requested"


class EventPublisher(Protocol):
    enabled: bool

    def publish_required(self, event_type: str, user_id: str, data: dict[str, Any]) -> bool:
        pass


class NoopEventPublisher:
    enabled = False

    def publish_required(self, event_type: str, user_id: str, data: dict[str, Any]) -> bool:
        return False


class RabbitMQEventPublisher:
    enabled = True

    def __init__(self, message_queue_url: str, timeout_seconds: float) -> None:
        self._message_queue_url = message_queue_url
        self._timeout_seconds = timeout_seconds

    def publish_required(self, event_type: str, user_id: str, data: dict[str, Any]) -> bool:
        try:
            self._publish(event_type, user_id, data)
            return True
        except Exception as exc:
            logger.warning("event_publish_failed event_type=%s error=%s", event_type, exc.__class__.__name__)
            return False

    def _publish(self, event_type: str, user_id: str, data: dict[str, Any]) -> None:
        import pika

        event = {
            "eventId": str(uuid4()),
            "eventType": event_type,
            "occurredAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "userId": user_id,
            "data": data,
        }
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
        finally:
            connection.close()


def create_event_publisher(message_queue_url: str, timeout_seconds: float) -> EventPublisher:
    if not message_queue_url:
        return NoopEventPublisher()
    return RabbitMQEventPublisher(message_queue_url, timeout_seconds)

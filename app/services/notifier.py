import logging
from typing import Protocol

from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)


def get_idempotency_key(event: OutboxEvent) -> str:
    """Return a stable idempotency key for an outbox event."""
    return str(event.id)


class EventNotifier(Protocol):
    """Interface for delivering outbox events."""

    async def deliver(self, event: OutboxEvent) -> None:
        """Deliver an event or raise an exception if delivery fails."""
        ...


class LoggingEventNotifier:
    """Development notifier that logs events instead of sending them."""

    async def deliver(self, event: OutboxEvent) -> None:
        logger.info(
            "Outbox event delivered to development notifier",
            extra={
                "event_id": str(event.id),
                "event_type": event.event_type,
                "organization_id": str(event.organization_id),
                "workflow_request_id": str(event.workflow_request_id),
            },
        )

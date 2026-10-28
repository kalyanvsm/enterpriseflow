import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.notifier import EventNotifier
from app.services.outbox import (
    claim_outbox_events,
    mark_outbox_event_delivered,
    schedule_outbox_retry,
)

logger = logging.getLogger(__name__)


async def dispatch_outbox_events(
    session: AsyncSession,
    notifier: EventNotifier,
    *,
    batch_size: int = 10,
    max_attempts: int = 5,
    retry_delay: timedelta = timedelta(minutes=1),
) -> int:
    """Deliver a batch of outbox events and return the number delivered."""
    events = await claim_outbox_events(session, batch_size=batch_size)
    delivered_count = 0

    for event in events:
        claim_token = event.claim_token
        if claim_token is None:
            logger.error(
                "Claimed outbox event has no claim token",
                extra={"event_id": str(event.id)},
            )
            continue

        try:
            await notifier.deliver(event)
        except Exception as exc:
            logger.exception(
                "Outbox event delivery failed",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                },
            )
            await schedule_outbox_retry(
                session,
                event.id,
                claim_token=claim_token,
                error=str(exc),
                max_attempts=max_attempts,
                retry_delay=retry_delay,
            )
        else:
            marked_delivered = await mark_outbox_event_delivered(
                session,
                event.id,
                claim_token=claim_token,
            )
            if marked_delivered:
                delivered_count += 1
            else:
                logger.warning(
                    "Outbox event claim expired before delivery was recorded",
                    extra={"event_id": str(event.id)},
                )

    return delivered_count

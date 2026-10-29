import logging
from datetime import timedelta
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.notifier import EventNotifier, get_idempotency_key
from app.services.outbox import (
    claim_outbox_events,
    mark_outbox_event_delivered,
    schedule_outbox_retry,
)
from app.services.outbox_results import RetryOutcome

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
    started_at = perf_counter()
    events = await claim_outbox_events(session, batch_size=batch_size)
    delivered_count = 0
    delivery_failed_count = 0
    retry_scheduled_count = 0
    retry_exhausted_count = 0
    claim_conflict_count = 0

    for event in events:
        claim_token = event.claim_token
        if claim_token is None:
            claim_conflict_count += 1
            logger.error(
                "Claimed outbox event has no claim token",
                extra={"event_id": str(event.id)},
            )
            continue

        try:
            await notifier.deliver(event, idempotency_key=get_idempotency_key(event))
        except Exception as exc:
            delivery_failed_count += 1
            logger.exception(
                "Outbox event delivery failed",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                },
            )
            retry_scheduled = await schedule_outbox_retry(
                session,
                event.id,
                claim_token=claim_token,
                error=str(exc),
                max_attempts=max_attempts,
                retry_delay=retry_delay,
            )
            if retry_scheduled == RetryOutcome.RETRY_SCHEDULED:
                retry_scheduled_count += 1
                logger.warning(
                    "Outbox event retry scheduled",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "attempts": event.attempts,
                        "max_attempts": max_attempts,
                    },
                )
            elif retry_scheduled == RetryOutcome.RETRY_EXHAUSTED:
                retry_exhausted_count += 1
                logger.error(
                    "Outbox event retries exhausted",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "attempts": event.attempts,
                        "max_attempts": max_attempts,
                    },
                )
            elif retry_scheduled == RetryOutcome.STALE_CLAIM:
                claim_conflict_count += 1
                logger.warning(
                    "Outbox event retry skipped due to stale claim",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                    },
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
                claim_conflict_count += 1
                logger.warning(
                    "Outbox event claim expired before delivery was recorded",
                    extra={"event_id": str(event.id)},
                )

    logger.info(
        "Outbox worker batch completed",
        extra={
            "claimed_count": len(events),
            "delivered_count": delivered_count,
            "delivery_failed_count": delivery_failed_count,
            "retry_scheduled_count": retry_scheduled_count,
            "retry_exhausted_count": retry_exhausted_count,
            "claim_conflict_count": claim_conflict_count,
            "duration_ms": round((perf_counter() - started_at) * 1000, 2),
        },
    )

    return delivered_count

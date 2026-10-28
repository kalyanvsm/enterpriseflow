import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox_event import OutboxEvent
from app.models.workflow_request import WorkflowRequest
from app.services.outbox_results import RetryOutcome


def record_outbox_event(
    workflow_request: WorkflowRequest,
    event_type: str,
) -> OutboxEvent:
    return OutboxEvent(
        organization_id=workflow_request.organization_id,
        workflow_request_id=workflow_request.id,
        event_type=event_type,
        payload={
            "request_id": str(workflow_request.id),
            "organization_id": str(workflow_request.organization_id),
            "title": workflow_request.title,
            "status": workflow_request.status,
        },
    )


async def claim_outbox_events(
    session: AsyncSession,
    *,
    batch_size: int = 10,
    lease_duration: timedelta = timedelta(minutes=5),
) -> list[OutboxEvent]:
    """Claim available outbox events for a worker."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    if lease_duration <= timedelta(0):
        raise ValueError("lease_duration must be positive")

    now = datetime.now(UTC)

    statement = (
        select(OutboxEvent)
        .where(
            OutboxEvent.available_at <= now,
            or_(
                OutboxEvent.status == "pending",
                (
                    (OutboxEvent.status == "processing")
                    & (
                        OutboxEvent.locked_until.is_(None)
                        | (OutboxEvent.locked_until <= now)
                    )
                ),
            ),
        )
        .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.scalars(statement)
    events = list(result.all())

    for event in events:
        event.status = "processing"
        event.locked_until = now + lease_duration
        event.claim_token = uuid.uuid4()
        event.attempts += 1

    await session.commit()

    return events


async def mark_outbox_event_delivered(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    claim_token: uuid.UUID,
) -> bool:
    """Mark a processing event as delivered."""
    event = await session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.id == event_id,
            OutboxEvent.status == "processing",
            OutboxEvent.claim_token == claim_token,
        )
        .with_for_update()
    )

    if event is None:
        return False

    event.status = "delivered"
    event.delivered_at = datetime.now(UTC)
    event.locked_until = None
    event.claim_token = None
    event.last_error = None

    await session.commit()
    return True


async def schedule_outbox_retry(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    claim_token: uuid.UUID,
    error: str,
    max_attempts: int = 5,
    retry_delay: timedelta = timedelta(minutes=1),
) -> RetryOutcome:
    """Schedule a retry, or mark the event failed after max attempts."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if retry_delay < timedelta(0):
        raise ValueError("retry_delay must not be negative")

    event = await session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.id == event_id,
            OutboxEvent.status == "processing",
            OutboxEvent.claim_token == claim_token,
        )
        .with_for_update()
    )

    if event is None:
        return RetryOutcome.STALE_CLAIM

    event.last_error = error[:2000]
    event.locked_until = None
    event.claim_token = None

    if event.attempts >= max_attempts:
        event.status = "failed"
        outcome = RetryOutcome.RETRY_EXHAUSTED
    else:
        event.status = "pending"
        event.available_at = datetime.now(UTC) + retry_delay
        outcome = RetryOutcome.RETRY_SCHEDULED

    await session.commit()
    return outcome

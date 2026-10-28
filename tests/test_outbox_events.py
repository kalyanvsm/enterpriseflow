import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OutboxEvent, User, WorkflowRequest
from app.services.outbox import (
    claim_outbox_events,
    mark_outbox_event_delivered,
    schedule_outbox_retry,
)
from app.services.outbox_results import RetryOutcome


async def create_request(session: AsyncSession) -> WorkflowRequest:
    organization = Organization(name="Outbox Test Organization")
    session.add(organization)
    await session.flush()

    user = User(
        organization_id=organization.id,
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash="test-hash",
    )
    session.add(user)
    await session.flush()

    request = WorkflowRequest(
        organization_id=organization.id,
        created_by_id=user.id,
        title="Test request",
        description="Request for outbox tests",
    )
    session.add(request)
    await session.flush()

    return request


@pytest.mark.asyncio
async def test_outbox_event_persists_with_defaults(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        saved = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )

        assert saved is not None
        assert saved.event_type == "workflow_request.submitted"
        assert saved.payload == {"request_id": str(saved.workflow_request_id)}
        assert saved.status == "pending"
        assert saved.attempts == 0
        assert saved.delivered_at is None
        assert saved.locked_until is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "attempts"),
    [
        ("unknown", 0),
        ("pending", -1),
    ],
)
async def test_outbox_rejects_invalid_status_or_attempts(
    test_session_factory,
    status: str,
    attempts: int,
):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
            status=status,
            attempts=attempts,
        )
        session.add(event)

        with pytest.raises(IntegrityError):
            await session.commit()

        await session.rollback()


@pytest.mark.asyncio
async def test_claim_outbox_event_marks_it_processing(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        claimed = await claim_outbox_events(
            session,
            batch_size=10,
            lease_duration=timedelta(minutes=5),
        )

        assert len(claimed) == 1
        assert claimed[0].id == event_id
        assert claimed[0].status == "processing"
        assert claimed[0].attempts == 1
        assert claimed[0].locked_until is not None
        assert claimed[0].claim_token is not None

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)

        assert saved is not None
        assert saved.status == "processing"
        assert saved.attempts == 1


@pytest.mark.asyncio
async def test_claim_reclaims_event_with_expired_lease(test_session_factory):
    original_claim_token = uuid.uuid4()

    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
            status="processing",
            attempts=1,
            locked_until=(datetime.now(UTC) - timedelta(minutes=1)),
            claim_token=original_claim_token,
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        claimed = await claim_outbox_events(session)

        assert len(claimed) == 1
        assert claimed[0].id == event_id
        assert claimed[0].status == "processing"
        assert claimed[0].attempts == 2
        assert claimed[0].locked_until is not None
        assert claimed[0].claim_token is not None
        assert claimed[0].claim_token != original_claim_token

    async with test_session_factory() as session:
        stale_delivery = await mark_outbox_event_delivered(
            session,
            event_id,
            claim_token=original_claim_token,
        )

        assert stale_delivery is False

        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "processing"
        assert saved.attempts == 2


@pytest.mark.asyncio
async def test_claim_skips_event_with_active_lease(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
            status="processing",
            attempts=1,
            locked_until=(datetime.now(UTC) + timedelta(minutes=5)),
        )
        session.add(event)
        await session.commit()

    async with test_session_factory() as session:
        claimed = await claim_outbox_events(session)

        assert claimed == []


@pytest.mark.asyncio
async def test_concurrent_workers_claim_distinct_events(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)

        events = [
            OutboxEvent(
                organization_id=request.organization_id,
                workflow_request_id=request.id,
                event_type=f"workflow_request.test_{index}",
                payload={"index": index},
            )
            for index in range(4)
        ]
        session.add_all(events)
        await session.commit()
        expected_ids = {event.id for event in events}

    async def claim_batch():
        async with test_session_factory() as session:
            return await claim_outbox_events(session, batch_size=2)

    first_batch, second_batch = await asyncio.gather(
        claim_batch(),
        claim_batch(),
    )

    first_ids = {event.id for event in first_batch}
    second_ids = {event.id for event in second_batch}

    assert len(first_ids) == 2
    assert len(second_ids) == 2
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == expected_ids


@pytest.mark.asyncio
async def test_claim_skips_row_locked_by_another_worker(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        events = [
            OutboxEvent(
                organization_id=request.organization_id,
                workflow_request_id=request.id,
                event_type=f"workflow_request.lock_test_{index}",
                payload={"index": index},
            )
            for index in range(2)
        ]
        session.add_all(events)
        await session.commit()
        locked_event_id = events[0].id
        available_event_id = events[1].id

    async with test_session_factory() as locking_session:
        await locking_session.begin()
        await locking_session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.id == locked_event_id)
            .with_for_update()
        )

        try:
            async with test_session_factory() as worker_session:
                claimed = await claim_outbox_events(
                    worker_session,
                    batch_size=1,
                )

                assert len(claimed) == 1
                assert claimed[0].id == available_event_id
        finally:
            await locking_session.rollback()


@pytest.mark.asyncio
async def test_mark_processing_event_delivered(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        claimed = await claim_outbox_events(session)
        assert len(claimed) == 1
        claim_token = claimed[0].claim_token
        assert claim_token is not None

    async with test_session_factory() as session:
        result = await mark_outbox_event_delivered(
            session,
            event_id,
            claim_token=claim_token,
        )
        assert result is True

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "delivered"
        assert saved.delivered_at is not None
        assert saved.locked_until is None
        assert saved.claim_token is None
        assert saved.last_error is None


@pytest.mark.asyncio
async def test_schedule_outbox_retry(test_session_factory):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        claimed = await claim_outbox_events(session)
        assert len(claimed) == 1
        claim_token = claimed[0].claim_token
        assert claim_token is not None

    async with test_session_factory() as session:
        result = await schedule_outbox_retry(
            session,
            event_id,
            claim_token=claim_token,
            error="Temporary delivery failure",
            max_attempts=5,
            retry_delay=timedelta(minutes=2),
        )
        assert result == RetryOutcome.RETRY_SCHEDULED

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "pending"
        assert saved.attempts == 1
        assert saved.available_at > datetime.now(UTC)
        assert saved.locked_until is None
        assert saved.claim_token is None
        assert saved.last_error == "Temporary delivery failure"


@pytest.mark.asyncio
async def test_retry_marks_event_failed_at_max_attempts(
    test_session_factory,
):
    claim_token = uuid.uuid4()

    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
            status="processing",
            attempts=5,
            locked_until=datetime.now(UTC) + timedelta(minutes=5),
            claim_token=claim_token,
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        result = await schedule_outbox_retry(
            session,
            event_id,
            claim_token=claim_token,
            error="Permanent failure after retries",
            max_attempts=5,
        )
        assert result == RetryOutcome.RETRY_EXHAUSTED

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "failed"
        assert saved.claim_token is None


@pytest.mark.asyncio
async def test_stale_worker_cannot_mark_reclaimed_event_delivered(
    test_session_factory,
):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    async with test_session_factory() as session:
        first_claim = await claim_outbox_events(session)
        assert len(first_claim) == 1
        old_token = first_claim[0].claim_token
        assert old_token is not None

    async with test_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None
        event.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with test_session_factory() as session:
        second_claim = await claim_outbox_events(session)
        assert len(second_claim) == 1
        new_token = second_claim[0].claim_token
        assert new_token is not None
        assert new_token != old_token

    async with test_session_factory() as session:
        result = await mark_outbox_event_delivered(
            session,
            event_id,
            claim_token=old_token,
        )
        assert result is False

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "processing"
        assert saved.claim_token == new_token

    async with test_session_factory() as session:
        result = await mark_outbox_event_delivered(
            session,
            event_id,
            claim_token=new_token,
        )
        assert result is True


@pytest.mark.asyncio
async def test_stale_worker_cannot_schedule_retry_for_reclaimed_event(
    test_session_factory,
):
    async with test_session_factory() as session:
        request = await create_request(session)
        event = OutboxEvent(
            organization_id=request.organization_id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    # Worker 1 claims the event.
    async with test_session_factory() as session:
        first_claim = await claim_outbox_events(session)
        assert len(first_claim) == 1
        old_token = first_claim[0].claim_token
        assert old_token is not None

    # Simulate the first worker's lease expiring.
    async with test_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None
        event.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    # Worker 2 reclaims the event with a new token.
    async with test_session_factory() as session:
        second_claim = await claim_outbox_events(session)
        assert len(second_claim) == 1
        new_token = second_claim[0].claim_token
        assert new_token is not None
        assert new_token != old_token

    # Worker 1 must not alter the event using its stale token.
    async with test_session_factory() as session:
        result = await schedule_outbox_retry(
            session,
            event_id,
            claim_token=old_token,
            error="Stale worker failure",
        )
        assert result == RetryOutcome.STALE_CLAIM

    # Verify worker 2 still owns the processing event.
    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "processing"
        assert saved.claim_token == new_token
        assert saved.last_error is None

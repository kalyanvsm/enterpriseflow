import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Organization, OutboxEvent, User, WorkflowRequest
from app.services.notifier import get_idempotency_key
from app.services.outbox import (
    claim_outbox_events,
    mark_outbox_event_delivered,
)


class FakeIdempotentProvider:
    """Simulate a provider that deduplicates requests by idempotency key."""

    def __init__(self):
        self.accepted_keys: set[str] = set()
        self.notifications_sent = 0

    async def send(self, event: OutboxEvent, *, idempotency_key: str) -> None:
        if idempotency_key in self.accepted_keys:
            return

        self.accepted_keys.add(idempotency_key)
        self.notifications_sent += 1


@pytest.mark.asyncio
async def test_provider_idempotency_prevents_duplicate_after_worker_crash(
    test_session_factory,
):
    async with test_session_factory() as session:
        organization = Organization(name=f"Idempotency test {uuid.uuid4()}")
        session.add(organization)
        await session.flush()

        user = User(
            organization_id=organization.id,
            email=f"idempotency-{uuid.uuid4()}@example.com",
            password_hash="test-hash",
            role="employee",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        request = WorkflowRequest(
            organization_id=organization.id,
            created_by_id=user.id,
            title="Test notification idempotency",
            description="Simulate a worker crash after provider acceptance.",
            status="pending",
        )
        session.add(request)
        await session.flush()

        event = OutboxEvent(
            organization_id=organization.id,
            workflow_request_id=request.id,
            event_type="workflow_request.submitted",
            payload={"request_id": str(request.id)},
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    provider = FakeIdempotentProvider()

    # Worker 1 claims the event and the provider accepts the notification.
    async with test_session_factory() as session:
        first_claim = await claim_outbox_events(session)
        assert len(first_claim) == 1

        first_event = first_claim[0]
        idempotency_key = get_idempotency_key(first_event)

        await provider.send(first_event, idempotency_key=idempotency_key)

        # Simulate a crash: deliberately do not mark the event delivered.

    assert provider.notifications_sent == 1

    # Simulate the lease expiring after the worker crashes.
    async with test_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None
        event.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    # Worker 2 reclaims the event and retries with the same stable key.
    async with test_session_factory() as session:
        second_claim = await claim_outbox_events(session)
        assert len(second_claim) == 1

        second_event = second_claim[0]
        second_key = get_idempotency_key(second_event)

        assert second_key == idempotency_key

        await provider.send(second_event, idempotency_key=second_key)

        # The provider recognizes the retry, so no duplicate is sent.
        assert provider.notifications_sent == 1

        marked_delivered = await mark_outbox_event_delivered(
            session,
            event_id,
            claim_token=second_event.claim_token,
        )
        assert marked_delivered is True

    async with test_session_factory() as session:
        saved = await session.get(OutboxEvent, event_id)
        assert saved is not None
        assert saved.status == "delivered"
        assert saved.attempts == 2
        assert saved.claim_token is None

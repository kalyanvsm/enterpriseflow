import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import select

from app.models import Organization, OutboxEvent, User, WorkflowRequest
from app.services.outbox_dispatcher import dispatch_outbox_events


def test_dispatcher_delivers_event_in_postgres(test_session_factory):
    async def scenario():
        async with test_session_factory() as session:
            organization = Organization(name=f"Dispatcher Integration {uuid4()}")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"dispatcher-{uuid4()}@example.com",
                password_hash="test-hash",
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.flush()

            request = WorkflowRequest(
                organization_id=organization.id,
                created_by_id=user.id,
                title="Dispatcher integration test",
                description="Verify delivery with PostgreSQL.",
                status="pending",
            )
            session.add(request)
            await session.flush()

            event = OutboxEvent(
                organization_id=organization.id,
                workflow_request_id=request.id,
                event_type="workflow_request.submitted",
                payload={
                    "request_id": str(request.id),
                    "organization_id": str(organization.id),
                    "title": request.title,
                    "status": request.status,
                },
            )
            session.add(event)
            await session.commit()
            event_id = event.id

        notifier = AsyncMock()
        notifier.deliver = AsyncMock()

        async with test_session_factory() as session:
            delivered_count = await dispatch_outbox_events(
                session,
                notifier,
                batch_size=10,
            )

        assert delivered_count == 1
        notifier.deliver.assert_awaited_once()

        async with test_session_factory() as session:
            persisted_event = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == event_id)
            )

            assert persisted_event is not None
            assert persisted_event.status == "delivered"
            assert persisted_event.attempts == 1
            assert persisted_event.claim_token is None
            assert persisted_event.locked_until is None
            assert persisted_event.delivered_at is not None

    asyncio.run(scenario())

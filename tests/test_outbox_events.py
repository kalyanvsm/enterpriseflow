
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OutboxEvent, User, WorkflowRequest


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

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.security import create_access_token, hash_password
from app.models import AuditLog, Organization, OutboxEvent, User, WorkflowRequest


@pytest.fixture
def authenticated_user(test_session_factory):
    import asyncio

    async def create_user():
        async with test_session_factory() as session:
            organization = Organization(name="Outbox Workflow Test Organization")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"outbox-{uuid4()}@example.com",
                password_hash=hash_password("Test-password-123"),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return {
                "user_id": str(user.id),
                "organization_id": str(organization.id),
                "token": create_access_token(str(user.id)),
            }

    return asyncio.run(create_user())


def test_submitting_request_records_outbox_event(
    client,
    authenticated_user,
    test_session_factory,
):
    headers = {
        "Authorization": f"Bearer {authenticated_user['token']}"
    }

    created = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Outbox integration test",
            "description": "Verify submission creates an outbox event.",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=headers,
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending"

    async def load_event():
        async with test_session_factory() as session:
            return await session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.workflow_request_id == request_id,
                    OutboxEvent.event_type == "workflow_request.submitted",
                )
            )

    import asyncio

    event = asyncio.run(load_event())

    assert event is not None
    assert event.status == "pending"
    assert event.attempts == 0
    assert event.payload["request_id"] == request_id
    assert event.payload["status"] == "pending"


def test_failed_outbox_insert_rolls_back_submission(
    client,
    authenticated_user,
    test_session_factory,
):
    headers = {
        "Authorization": f"Bearer {authenticated_user['token']}"
    }

    created = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Outbox rollback test",
            "description": "The failed outbox insert must roll back submission.",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    async def install_test_trigger():
        async with test_session_factory() as session:
            await session.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION reject_test_outbox_event()
                    RETURNS TRIGGER
                    LANGUAGE plpgsql
                    AS $$
                    BEGIN
                        RAISE EXCEPTION 'Simulated outbox failure';
                    END;
                    $$
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER reject_test_outbox_event_trigger
                    BEFORE INSERT ON outbox_events
                    FOR EACH ROW
                    EXECUTE FUNCTION reject_test_outbox_event()
                    """
                )
            )
            await session.commit()

    async def remove_test_trigger():
        async with test_session_factory() as session:
            await session.execute(
                text(
                    """
                    DROP TRIGGER IF EXISTS reject_test_outbox_event_trigger
                    ON outbox_events
                    """
                )
            )
            await session.execute(
                text(
                    """
                    DROP FUNCTION IF EXISTS reject_test_outbox_event()
                    """
                )
            )
            await session.commit()

    async def inspect_database():
        async with test_session_factory() as session:
            request = await session.scalar(
                select(WorkflowRequest).where(
                    WorkflowRequest.id == request_id
                )
            )
            audit_logs = (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.workflow_request_id == request_id,
                        AuditLog.action == "submitted",
                    )
                )
            ).all()
            events = (
                await session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.workflow_request_id == request_id,
                        OutboxEvent.event_type == "workflow_request.submitted",
                    )
                )
            ).all()
            return request, audit_logs, events

    asyncio.run(install_test_trigger())
    try:
        with pytest.raises(DBAPIError):
            client.post(
                f"/api/v1/requests/{request_id}/submit",
                headers=headers,
            )

        request, audit_logs, events = asyncio.run(inspect_database())

        assert request is not None
        assert request.status == "draft"
        assert audit_logs == []
        assert events == []
    finally:
        asyncio.run(remove_test_trigger())

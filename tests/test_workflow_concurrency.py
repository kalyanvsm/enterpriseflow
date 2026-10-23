
import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models import Organization, User
from app.models.audit_log import AuditLog
from app.models.workflow_request import WorkflowRequest
from app.services.workflow_request import decide_workflow_request


@pytest.mark.asyncio
async def test_concurrent_decisions_create_only_one_decision_audit(
    test_session_factory,
):
    # Create the organization, employee, admin, and pending request.
    async with test_session_factory() as session:
        organization = Organization(name=f"Concurrency-{uuid4()}")
        session.add(organization)
        await session.flush()

        employee = User(
            organization_id=organization.id,
            email=f"employee-{uuid4()}@example.com",
            password_hash=hash_password("Test-password-123"),
            role="employee",
            is_active=True,
        )
        admin = User(
            organization_id=organization.id,
            email=f"admin-{uuid4()}@example.com",
            password_hash=hash_password("Test-password-123"),
            role="admin",
            is_active=True,
        )
        session.add_all([employee, admin])
        await session.flush()

        request = WorkflowRequest(
            organization_id=organization.id,
            created_by_id=employee.id,
            title="Concurrent decision test",
            description="Two admins decisions must not both succeed.",
            status="pending",
        )
        session.add(request)
        await session.commit()

        request_id = request.id
        organization_id = organization.id
        admin_id = admin.id

    # Re-load the admin independently in each session.
    async def decide(decision: str) -> str:
        async with test_session_factory() as session:
            admin = await session.get(User, admin_id)
            assert admin is not None

            try:
                result = await decide_workflow_request(
                    session=session,
                    request_id=request_id,
                    current_user=admin,
                    decision=decision,
                )
                return result.status
            except HTTPException as exc:
                if exc.status_code == 409:
                    return "conflict"
                raise

    # Release both tasks together to make their operations overlap.
    start = asyncio.Event()

    async def start_decision(decision: str) -> str:
        await start.wait()
        return await decide(decision)

    first = asyncio.create_task(start_decision("approved"))
    second = asyncio.create_task(start_decision("rejected"))
    start.set()

    results = await asyncio.gather(first, second)

    assert results.count("conflict") == 1
    assert sum(result in {"approved", "rejected"} for result in results) == 1

    async with test_session_factory() as session:
        request_result = await session.get(WorkflowRequest, request_id)
        assert request_result is not None
        assert request_result.status in {"approved", "rejected"}

        decision_count = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.workflow_request_id == request_id,
                AuditLog.organization_id == organization_id,
                AuditLog.action.in_(["approved", "rejected"]),
            )
        )
        assert decision_count == 1

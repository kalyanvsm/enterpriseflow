from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.workflow_request import WorkflowRequest
from app.schemas.workflow_request import WorkflowRequestCreate


async def create_workflow_request(
    session: AsyncSession,
    request_data: WorkflowRequestCreate,
    current_user: User,
) -> WorkflowRequest:
    workflow_request = WorkflowRequest(
        organization_id=current_user.organization_id,
        created_by_id=current_user.id,
        title=request_data.title,
        description=request_data.description,
        status="draft",
    )

    session.add(workflow_request)
    await session.commit()
    await session.refresh(workflow_request)

    return workflow_request


async def list_workflow_requests(
    session: AsyncSession,
    organization_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[WorkflowRequest]:
    statement = (
        select(WorkflowRequest)
        .where(WorkflowRequest.organization_id == organization_id)
        .order_by(WorkflowRequest.created_at.desc(), WorkflowRequest.id)
        .limit(limit)
        .offset(offset)
    )

    result = await session.scalars(statement)
    return list(result.all())


async def submit_workflow_request(
    session: AsyncSession,
    request_id: UUID,
    current_user: User,
) -> WorkflowRequest:
    statement = (
        select(WorkflowRequest)
        .where(
            WorkflowRequest.id == request_id,
            WorkflowRequest.organization_id == current_user.organization_id,
            WorkflowRequest.created_by_id == current_user.id,
        )
        .with_for_update()
    )

    result = await session.scalars(statement)
    workflow_request = result.one_or_none()

    if workflow_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow request not found",
        )

    if workflow_request.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft requests can be submitted",
        )

    previous_status = workflow_request.status
    workflow_request.status = "pending"

    session.add(
        record_workflow_transition(
            workflow_request=workflow_request,
            actor=current_user,
            action="submitted",
            from_status=previous_status,
            to_status="pending",
        )
    )

    await session.commit()
    await session.refresh(workflow_request)

    return workflow_request


async def decide_workflow_request(
    session: AsyncSession,
    request_id: UUID,
    current_user: User,
    decision: str,
) -> WorkflowRequest:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Unsupported workflow decision")

    statement = (
        select(WorkflowRequest)
        .where(
            WorkflowRequest.id == request_id,
            WorkflowRequest.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )

    result = await session.scalars(statement)
    workflow_request = result.one_or_none()

    if workflow_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow request not found",
        )

    if workflow_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending requests can be approved or rejected",
        )

    previous_status = workflow_request.status
    workflow_request.status = decision

    session.add(
        record_workflow_transition(
            workflow_request=workflow_request,
            actor=current_user,
            action=decision,
            from_status=previous_status,
            to_status=decision,
        )
    )

    await session.commit()
    await session.refresh(workflow_request)

    return workflow_request


def record_workflow_transition(
    workflow_request: WorkflowRequest,
    actor: User,
    action: str,
    from_status: str,
    to_status: str,
) -> AuditLog:
    return AuditLog(
        organization_id=workflow_request.organization_id,
        workflow_request_id=workflow_request.id,
        actor_user_id=actor.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
    )


async def list_workflow_request_audit_logs(
    session: AsyncSession,
    request_id: UUID,
    organization_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    request_statement = select(WorkflowRequest.id).where(
        WorkflowRequest.id == request_id,
        WorkflowRequest.organization_id == organization_id,
    )
    request_result = await session.execute(request_statement)

    if request_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow request not found",
        )

    statement = (
        select(AuditLog)
        .where(
            AuditLog.workflow_request_id == request_id,
            AuditLog.organization_id == organization_id,
        )
        .order_by(AuditLog.created_at, AuditLog.id)
        .limit(limit)
        .offset(offset)
    )

    result = await session.scalars(statement)
    return list(result.all())

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

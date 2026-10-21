from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.workflow_request import (
    WorkflowRequestCreate,
    WorkflowRequestResponse,
)
from app.services.workflow_request import (
    create_workflow_request,
    list_workflow_requests,
)

router = APIRouter(
    prefix="/requests",
    tags=["workflow requests"],
)


@router.post(
    "",
    response_model=WorkflowRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_request_endpoint(
    request_data: WorkflowRequestCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> WorkflowRequestResponse:
    return await create_workflow_request(
        session,
        request_data,
        current_user,
    )


@router.get(
    "",
    response_model=list[WorkflowRequestResponse],
)
async def list_workflow_requests_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[WorkflowRequestResponse]:
    return await list_workflow_requests(
        session=session,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )

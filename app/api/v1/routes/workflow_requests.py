from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse
from app.schemas.workflow_request import (
    WorkflowRequestCreate,
    WorkflowRequestResponse,
)
from app.services.workflow_request import (
    create_workflow_request,
    decide_workflow_request,
    list_workflow_request_audit_logs,
    list_workflow_requests,
    submit_workflow_request,
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


@router.post(
    "/{request_id}/submit",
    response_model=WorkflowRequestResponse,
)
async def submit_workflow_request_endpoint(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> WorkflowRequestResponse:
    return await submit_workflow_request(
        session=session,
        request_id=request_id,
        current_user=current_user,
    )


@router.post(
    "/{request_id}/approve",
    response_model=WorkflowRequestResponse,
)
async def approve_workflow_request_endpoint(
    request_id: UUID,
    current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
) -> WorkflowRequestResponse:
    return await decide_workflow_request(
        session=session,
        request_id=request_id,
        current_user=current_user,
        decision="approved",
    )


@router.post(
    "/{request_id}/reject",
    response_model=WorkflowRequestResponse,
)
async def reject_workflow_request_endpoint(
    request_id: UUID,
    current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
) -> WorkflowRequestResponse:
    return await decide_workflow_request(
        session=session,
        request_id=request_id,
        current_user=current_user,
        decision="rejected",
    )


@router.get(
    "/{request_id}/audit-logs",
    response_model=list[AuditLogResponse],
)
async def get_workflow_request_audit_logs_endpoint(
    request_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    return await list_workflow_request_audit_logs(
        session=session,
        request_id=request_id,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
    )

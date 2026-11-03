
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.workflow_request import WorkflowRequest

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return workflow request counts for the current user's organization."""
    organization_id = current_user.organization_id

    statement = (
        select(
            func.count(WorkflowRequest.id).label("total"),
            func.count(WorkflowRequest.id)
            .filter(WorkflowRequest.status == "pending")
            .label("pending"),
            func.count(WorkflowRequest.id)
            .filter(WorkflowRequest.status == "approved")
            .label("approved"),
            func.count(WorkflowRequest.id)
            .filter(WorkflowRequest.status == "rejected")
            .label("rejected"),
        )
        .where(WorkflowRequest.organization_id == organization_id)
    )

    result = await session.execute(statement)
    counts = result.one()

    return {
        "total_requests": counts.total,
        "pending_approvals": counts.pending,
        "approved_requests": counts.approved,
        "rejected_requests": counts.rejected,
    }

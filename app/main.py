from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.organizations import router as organizations_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.workflow_requests import router as workflow_requests_router
from app.db.session import get_db

app = FastAPI(
    title="EnterpriseFlow API",
    description="Enterprise workflow and approval platform",
    version="0.1.0",
)


@app.get("/api/v1/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Check whether the API process is running."""
    return {"status": "ok"}


@app.get("/api/v1/ready", tags=["Health"])
async def readiness_check(
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Check whether the API can reach its database."""
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from exc

    return {"status": "ready"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(workflow_requests_router, prefix="/api/v1")

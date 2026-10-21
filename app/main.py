from fastapi import FastAPI

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.organizations import router as organizations_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.workflow_requests import router as workflow_requests_router

app = FastAPI(
    title="EnterpriseFlow API",
    description="Enterprise workflow and approval platform",
    version="0.1.0",
)


@app.get("/api/v1/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """
    Health check endpoint to verify that the API is running.
    """
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(workflow_requests_router, prefix="/api/v1")

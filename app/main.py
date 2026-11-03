from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.organizations import router as organizations_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.workflow_requests import router as workflow_requests_router
from app.db.session import get_db
from app.ui.dependencies import UIAuthenticationError
from app.ui.routes import router as ui_router

app = FastAPI(
    title="EnterpriseFlow API",
    description="Enterprise workflow and approval platform",
    version="0.1.0",
)


@app.exception_handler(UIAuthenticationError)
async def ui_auth_exception_handler(
    request: Request,
    exc: UIAuthenticationError,
) -> Response:
    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=status.HTTP_200_OK)
        response.headers["HX-Redirect"] = "/login"
        response.delete_cookie(key="access_token", path="/")
        return response

    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", path="/")
    return response


static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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


# REST API routes
app.include_router(auth_router, prefix="/api/v1")
app.include_router(organizations_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(workflow_requests_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")

# Python UI routes
app.include_router(ui_router)

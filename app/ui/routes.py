from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.models.workflow_request import WorkflowRequest
from app.schemas.auth import LoginRequest
from app.schemas.workflow_request import WorkflowRequestCreate
from app.services.auth import authenticate_user
from app.services.workflow_request import (
    create_workflow_request,
    decide_workflow_request,
    list_workflow_requests,
    submit_workflow_request,
)
from app.ui.dependencies import get_current_ui_user, get_optional_ui_user

templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(tags=["UI"], default_response_class=HTMLResponse)


async def fetch_dashboard_stats(
    session: AsyncSession,
    organization_id: UUID,
) -> dict[str, int]:
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


async def fetch_organization_requests(
    session: AsyncSession,
    organization_id: UUID,
) -> list[WorkflowRequest]:
    return await list_workflow_requests(
        session=session,
        organization_id=organization_id,
        limit=100,
        offset=0,
    )


async def fetch_pending_requests(
    session: AsyncSession,
    organization_id: UUID,
) -> list[WorkflowRequest]:
    statement = (
        select(WorkflowRequest)
        .where(
            WorkflowRequest.organization_id == organization_id,
            WorkflowRequest.status == "pending",
        )
        .order_by(WorkflowRequest.created_at.desc(), WorkflowRequest.id)
    )
    result = await session.scalars(statement)
    return list(result.all())


@router.get("/", response_class=RedirectResponse)
async def root_redirect(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    user = await get_optional_ui_user(request, session)
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    user = await get_optional_ui_user(request, session)
    if user is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "email": ""},
    )


@router.post("/login")
async def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    session: AsyncSession = Depends(get_db),
) -> Response:
    normalized_email = email.strip()

    if not normalized_email or not password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Please enter your email and password.",
                "email": normalized_email,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    access_token = await authenticate_user(
        session,
        LoginRequest(email=normalized_email, password=password),
    )

    if access_token is None:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Invalid email or password.",
                "email": normalized_email,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    max_age = 60 * 60 * 24 * 14 if remember_me else None
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    return response


@router.get("/logout")
@router.post("/logout")
def handle_logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", path="/")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    tab: str = Query(default="overview"),
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    is_admin = current_user.role == "admin"
    is_htmx = request.headers.get("HX-Request") == "true"

    if tab == "requests":
        requests_list = await fetch_organization_requests(
            session, current_user.organization_id
        )
        context = {
            "request": request,
            "user": current_user,
            "active_tab": "requests",
            "page_title": "Workflow requests",
            "requests": requests_list,
            "error": None,
            "success": None,
        }
        if is_htmx:
            return templates.TemplateResponse(
                request=request,
                name="dashboard/partials/requests.html",
                context=context,
            )
        return templates.TemplateResponse(
            request=request,
            name="dashboard/index.html",
            context=context,
        )

    if tab == "approvals":
        pending_list = await fetch_pending_requests(
            session, current_user.organization_id
        )
        context = {
            "request": request,
            "user": current_user,
            "active_tab": "approvals",
            "page_title": "Approvals",
            "pending_requests": pending_list,
            "is_admin": is_admin,
            "error": None,
            "success": None,
        }
        if is_htmx:
            return templates.TemplateResponse(
                request=request,
                name="dashboard/partials/approvals.html",
                context=context,
            )
        return templates.TemplateResponse(
            request=request,
            name="dashboard/index.html",
            context=context,
        )

    # Default to overview
    counts = await fetch_dashboard_stats(session, current_user.organization_id)
    context = {
        "request": request,
        "user": current_user,
        "active_tab": "overview",
        "page_title": "Overview",
        "counts": counts,
        "error": None,
    }
    if is_htmx:
        return templates.TemplateResponse(
            request=request,
            name="dashboard/partials/overview.html",
            context=context,
        )
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context=context,
    )


@router.get("/dashboard/overview", response_class=HTMLResponse)
async def dashboard_overview_tab(
    request: Request,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    counts = await fetch_dashboard_stats(session, current_user.organization_id)
    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/overview.html",
        context={
            "request": request,
            "user": current_user,
            "counts": counts,
            "error": None,
        },
    )


@router.get("/dashboard/requests", response_class=HTMLResponse)
async def dashboard_requests_tab(
    request: Request,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    requests_list = await fetch_organization_requests(
        session, current_user.organization_id
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/requests.html",
        context={
            "request": request,
            "user": current_user,
            "requests": requests_list,
            "error": None,
            "success": None,
        },
    )


@router.get("/dashboard/approvals", response_class=HTMLResponse)
async def dashboard_approvals_tab(
    request: Request,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    pending_list = await fetch_pending_requests(
        session, current_user.organization_id
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/approvals.html",
        context={
            "request": request,
            "user": current_user,
            "pending_requests": pending_list,
            "is_admin": current_user.role == "admin",
            "error": None,
            "success": None,
        },
    )


@router.post("/dashboard/requests")
async def create_request_ui(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    trimmed_title = title.strip()
    trimmed_desc = description.strip()

    error = None
    success = None

    if len(trimmed_title) < 3 or len(trimmed_title) > 200:
        error = "Title must be between 3 and 200 characters."
    elif not trimmed_desc or len(trimmed_desc) > 10000:
        error = "Description is required and must be at most 10,000 characters."
    else:
        try:
            await create_workflow_request(
                session,
                WorkflowRequestCreate(title=trimmed_title, description=trimmed_desc),
                current_user,
            )
            success = "Draft request created successfully."
        except HTTPException as exc:
            error = exc.detail
        except Exception:
            error = "Something went wrong while creating the request."

    requests_list = await fetch_organization_requests(
        session, current_user.organization_id
    )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url="/dashboard?tab=requests",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/requests_table.html",
        context={
            "request": request,
            "user": current_user,
            "requests": requests_list,
            "error": error,
            "success": success,
        },
    )


@router.post("/dashboard/requests/{request_id}/submit")
async def submit_request_ui(
    request: Request,
    request_id: UUID,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    error = None
    success = None

    try:
        await submit_workflow_request(
            session=session,
            request_id=request_id,
            current_user=current_user,
        )
        success = "Request submitted for approval."
    except HTTPException as exc:
        error = exc.detail
    except Exception:
        error = "Something went wrong while submitting the request."

    requests_list = await fetch_organization_requests(
        session, current_user.organization_id
    )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url="/dashboard?tab=requests",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/requests_table.html",
        context={
            "request": request,
            "user": current_user,
            "requests": requests_list,
            "error": error,
            "success": success,
        },
    )


@router.post("/dashboard/requests/{request_id}/approve")
async def approve_request_ui(
    request: Request,
    request_id: UUID,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    is_admin = current_user.role == "admin"
    error = None
    success = None

    if not is_admin:
        error = "You do not have permission to decide this request."
    else:
        try:
            await decide_workflow_request(
                session=session,
                request_id=request_id,
                current_user=current_user,
                decision="approved",
            )
            success = "Request approved successfully."
        except HTTPException as exc:
            error = exc.detail
        except Exception:
            error = "Something went wrong while approving the request."

    pending_list = await fetch_pending_requests(
        session, current_user.organization_id
    )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url="/dashboard?tab=approvals",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/approvals_table.html",
        context={
            "request": request,
            "user": current_user,
            "pending_requests": pending_list,
            "is_admin": is_admin,
            "error": error,
            "success": success,
        },
    )


@router.post("/dashboard/requests/{request_id}/reject")
async def reject_request_ui(
    request: Request,
    request_id: UUID,
    current_user: User = Depends(get_current_ui_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    is_admin = current_user.role == "admin"
    error = None
    success = None

    if not is_admin:
        error = "You do not have permission to decide this request."
    else:
        try:
            await decide_workflow_request(
                session=session,
                request_id=request_id,
                current_user=current_user,
                decision="rejected",
            )
            success = "Request rejected successfully."
        except HTTPException as exc:
            error = exc.detail
        except Exception:
            error = "Something went wrong while rejecting the request."

    pending_list = await fetch_pending_requests(
        session, current_user.organization_id
    )

    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(
            url="/dashboard?tab=approvals",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard/partials/approvals_table.html",
        context={
            "request": request,
            "user": current_user,
            "pending_requests": pending_list,
            "is_admin": is_admin,
            "error": error,
            "success": success,
        },
    )


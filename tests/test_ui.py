import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.user import User

PASSWORD = "SecurePassword1234!"


def create_user(test_session_factory, email: str, role: str = "employee") -> User:
    async def _create() -> User:
        async with test_session_factory() as session:
            org = Organization(name=f"Org {uuid4()}")
            session.add(org)
            await session.flush()

            user = User(
                organization_id=org.id,
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_root_redirects_unauthenticated_to_login(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_renders_form(client: TestClient) -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign in to EnterpriseFlow" in response.text
    assert 'name="email"' in response.text
    assert 'name="password"' in response.text


def test_login_invalid_credentials_returns_error(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "wrong"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.text


def test_login_success_sets_cookie_and_redirects(
    client: TestClient,
    test_session_factory,
) -> None:
    user = create_user(test_session_factory, f"user_{uuid4()}@example.com")

    response = client.post(
        "/login",
        data={"email": user.email, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "access_token" in response.cookies


def test_authenticated_user_accesses_dashboard(
    client: TestClient,
    test_session_factory,
) -> None:
    user = create_user(test_session_factory, f"emp_{uuid4()}@example.com")
    token = create_access_token(str(user.id))
    client.cookies.set("access_token", token)

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert user.email in response.text
    assert "Welcome to EnterpriseFlow" in response.text
    assert "Total requests" in response.text


def test_dashboard_requests_flow_and_htmx(
    client: TestClient,
    test_session_factory,
) -> None:
    user = create_user(test_session_factory, f"requester_{uuid4()}@example.com")
    token = create_access_token(str(user.id))
    client.cookies.set("access_token", token)

    # 1. View requests tab
    response = client.get("/dashboard?tab=requests")
    assert response.status_code == 200
    assert "Workflow requests" in response.text
    assert "Create a workflow request" in response.text

    # 2. Create a request via HTMX
    create_resp = client.post(
        "/dashboard/requests",
        data={"title": "Ergonomic Chair", "description": "Needs lumbar support"},
        headers={"HX-Request": "true"},
    )
    assert create_resp.status_code == 200
    assert "Draft request created successfully." in create_resp.text
    assert "Ergonomic Chair" in create_resp.text
    assert "Submit for approval" in create_resp.text


def test_admin_approvals_flow_and_htmx(
    client: TestClient,
    test_session_factory,
) -> None:
    admin = create_user(
        test_session_factory,
        f"admin_{uuid4()}@example.com",
        role="admin",
    )
    token = create_access_token(str(admin.id))
    client.cookies.set("access_token", token)

    # 1. Create a request
    client.post(
        "/dashboard/requests",
        data={"title": "Cloud Server Upgrade", "description": "Production scale"},
        headers={"HX-Request": "true"},
    )

    # 2. List requests to find ID
    resp = client.get("/dashboard/requests", headers={"HX-Request": "true"})
    assert resp.status_code == 200

    # Submit via REST API or direct UI submit
    from sqlalchemy import select

    from app.models.workflow_request import WorkflowRequest

    async def get_req_id():
        async with test_session_factory() as s:
            r = await s.scalars(
                select(WorkflowRequest).where(
                    WorkflowRequest.title == "Cloud Server Upgrade"
                )
            )
            return r.first().id

    req_id = asyncio.run(get_req_id())

    # Submit the request
    submit_resp = client.post(
        f"/dashboard/requests/{req_id}/submit",
        headers={"HX-Request": "true"},
    )
    assert submit_resp.status_code == 200
    assert "Request submitted for approval." in submit_resp.text

    # Check approvals tab
    approvals_resp = client.get("/dashboard/approvals", headers={"HX-Request": "true"})
    assert approvals_resp.status_code == 200
    assert "Cloud Server Upgrade" in approvals_resp.text
    assert "Approve" in approvals_resp.text
    assert "Reject" in approvals_resp.text

    # Admin approves
    approve_resp = client.post(
        f"/dashboard/requests/{req_id}/approve",
        headers={"HX-Request": "true"},
    )
    assert approve_resp.status_code == 200
    assert "Request approved successfully." in approve_resp.text
    assert "All caught up" in approve_resp.text


def test_logout_clears_cookie(client: TestClient) -> None:
    client.cookies.set("access_token", "fake-token")
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    # Verify cookie is cleared/expired
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie

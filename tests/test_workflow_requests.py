from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models import Organization, User


@pytest.fixture
def authenticated_user(test_session_factory):
    import asyncio

    async def create_user():
        async with test_session_factory() as session:
            organization = Organization(name="Workflow Test Organization")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"workflow-{uuid4()}@example.com",
                password_hash=hash_password("Test-password-123"),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return {
                "user_id": str(user.id),
                "organization_id": str(organization.id),
                "token": create_access_token(str(user.id)),
            }

    return asyncio.run(create_user())


@pytest.fixture
def authenticated_admin(test_session_factory):
    import asyncio

    async def create_admin():
        async with test_session_factory() as session:
            organization = Organization(name="Admin Test Organization")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"admin-{uuid4()}@example.com",
                password_hash=hash_password("Admin-password-123"),
                role="admin",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return {
                "user_id": str(user.id),
                "organization_id": str(organization.id),
                "token": create_access_token(str(user.id)),
            }

    return asyncio.run(create_admin())


@pytest.fixture
def admin_in_same_organization(
    test_session_factory,
    authenticated_user: dict,
):
    import asyncio

    async def create_admin():
        async with test_session_factory() as session:
            user = User(
                organization_id=authenticated_user["organization_id"],
                email=f"admin-{uuid4()}@example.com",
                password_hash=hash_password("Admin-password-123"),
                role="admin",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return {
                "user_id": str(user.id),
                "organization_id": authenticated_user["organization_id"],
                "token": create_access_token(str(user.id)),
            }

    return asyncio.run(create_admin())


def test_create_workflow_request_require_authentication(client: TestClient):
    response = client.post(
        "/api/v1/requests",
        json={
            "title": "Purchase new laptops",
            "description": "Request laptops for the engineering team.",
        },
    )

    assert response.status_code == 401


def test_create_workflow_request_creates_draft_for_current_user(
    client: TestClient,
    authenticated_user: dict,
):
    response = client.post(
        "/api/v1/requests",
        headers={"Authorization": f"Bearer {authenticated_user['token']}"},
        json={
            "title": "Purchase new laptops",
            "description": "Request laptops for the engineering team.",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["title"] == "Purchase new laptops"
    assert data["status"] == "draft"
    assert data["organization_id"] == authenticated_user["organization_id"]
    assert data["created_by_id"] == authenticated_user["user_id"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_workflow_request_ignores_untrusted_fields(
    client: TestClient,
    authenticated_user: dict,
):
    response = client.post(
        "/api/v1/requests",
        headers={"Authorization": f"Bearer {authenticated_user['token']}"},
        json={
            "title": "Purchase new laptops",
            "description": "Request laptops for the engineering team.",
            "organization_id": str(uuid4()),
            "created_by_id": str(uuid4()),
            "status": "approved",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["organization_id"] == authenticated_user["organization_id"]
    assert data["created_by_id"] == authenticated_user["user_id"]
    assert data["status"] == "draft"


def test_list_workflow_requests_requires_authentication(client: TestClient):
    response = client.get("/api/v1/requests")

    assert response.status_code == 401


def test_list_workflow_requests_returns_only_current_organization(
    client: TestClient,
    authenticated_user: dict,
    test_session_factory,
):
    import asyncio
    from uuid import uuid4

    from app.core.security import create_access_token, hash_password
    from app.models import Organization, User

    first_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    first_response = client.post(
        "/api/v1/requests",
        headers=first_headers,
        json={
            "title": "Organization A request",
            "description": "Belongs to the first organization.",
        },
    )
    assert first_response.status_code == 201

    async def create_second_user():
        async with test_session_factory() as session:
            organization = Organization(name="Second Test Organization")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"second-{uuid4()}@example.com",
                password_hash=hash_password("Test-password-123!"),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return {
                "organization_id": str(organization.id),
                "token": create_access_token(str(user.id)),
            }

    second_user = asyncio.run(create_second_user())
    second_headers = {"Authorization": f"Bearer {second_user['token']}"}

    second_response = client.post(
        "/api/v1/requests",
        headers=second_headers,
        json={
            "title": "Organization B request",
            "description": "Belongs to the second organization.",
        },
    )
    assert second_response.status_code == 201

    first_list = client.get("/api/v1/requests", headers=first_headers)
    second_list = client.get("/api/v1/requests", headers=second_headers)

    assert first_list.status_code == 200
    assert second_list.status_code == 200

    first_items = first_list.json()
    second_items = second_list.json()

    assert [item["title"] for item in first_items] == ["Organization A request"]
    assert [item["title"] for item in second_items] == ["Organization B request"]

    assert all(
        item["organization_id"] == authenticated_user["organization_id"]
        for item in first_items
    )
    assert all(
        item["organization_id"] == second_user["organization_id"]
        for item in second_items
    )


def test_list_workflow_requests_supports_pagination(
    client: TestClient,
    authenticated_user: dict,
):
    headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    for number in range(3):
        response = client.post(
            "/api/v1/requests",
            headers=headers,
            json={
                "title": f"Test request {number}",
                "description": "Request created for pagination testing.",
            },
        )
        assert response.status_code == 201

    response = client.get(
        "/api/v1/requests?limit=2&offset=0",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.get(
        "/api/v1/requests?limit=2&offset=2",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_submit_workflow_request_changes_draft_to_pending(
    client: TestClient,
    authenticated_user: dict,
):
    headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    create_response = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Submit for approval",
            "description": "This draft should become pending.",
        },
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_submit_workflow_request_cannot_be_repeated(
    client: TestClient,
    authenticated_user: dict,
):
    headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    create_response = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Submit only once",
            "description": "A second submission should conflict.",
        },
    )
    request_id = create_response.json()["id"]

    first_response = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=headers,
    )
    second_response = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409


def test_submit_workflow_request_requires_authentication(
    client: TestClient,
    authenticated_user: dict,
):
    headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    create_response = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Protected submission",
            "description": "Submission requires authentication.",
        },
    )
    request_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/requests/{request_id}/submit",
    )

    assert response.status_code == 401


def test_user_cannot_submit_another_users_request(
    client: TestClient,
    authenticated_user: dict,
    test_session_factory,
):
    import asyncio
    from uuid import uuid4

    from app.core.security import create_access_token, hash_password
    from app.models import Organization, User

    owner_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    create_response = client.post(
        "/api/v1/requests",
        headers=owner_headers,
        json={
            "title": "Owner's private request",
            "description": "Only the creator should submit this request.",
        },
    )
    assert create_response.status_code == 201
    request_id = create_response.json()["id"]

    async def create_other_user():
        async with test_session_factory() as session:
            organization = Organization(name="Unauthorized Test Organization")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=f"unauthorized-{uuid4()}@example.com",
                password_hash=hash_password("Test-password-123!"),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            return create_access_token(str(user.id))

    other_token = asyncio.run(create_other_user())

    response = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404

    owner_list = client.get(
        "/api/v1/requests",
        headers=owner_headers,
    )
    assert owner_list.status_code == 200

    original_request = next(
        item for item in owner_list.json() if item["id"] == request_id
    )
    assert original_request["status"] == "draft"


def test_employee_cannot_approve_request(
    client: TestClient,
    authenticated_user: dict,
):
    headers = {"Authorization": f"Bearer {authenticated_user['token']}"}

    created = client.post(
        "/api/v1/requests",
        headers=headers,
        json={
            "title": "Approval permission test",
            "description": "An employee cannot approve this request.",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["id"]
    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=headers,
    )
    assert submitted.status_code == 200

    response = client.post(
        f"/api/v1/requests/{request_id}/approve",
        headers=headers,
    )

    assert response.status_code == 403


def test_admin_can_approve_pending_request(
    client: TestClient,
    authenticated_user: dict,
    admin_in_same_organization: dict,
):
    owner_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
    admin_headers = {"Authorization": f"Bearer {admin_in_same_organization['token']}"}

    created = client.post(
        "/api/v1/requests",
        headers=owner_headers,
        json={
            "title": "Approve this request",
            "description": "This request should be approved by an admin.",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["id"]
    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=owner_headers,
    )
    assert submitted.status_code == 200

    response = client.post(
        f"/api/v1/requests/{request_id}/approve",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_admin_can_reject_pending_request(
    client: TestClient,
    authenticated_user: dict,
    admin_in_same_organization: dict,
):
    owner_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
    admin_headers = {"Authorization": f"Bearer {admin_in_same_organization['token']}"}

    created = client.post(
        "/api/v1/requests",
        headers=owner_headers,
        json={
            "title": "Reject this request",
            "description": "This request should be rejected by an admin",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["id"]
    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=owner_headers,
    )
    assert submitted.status_code == 200

    response = client.post(
        f"/api/v1/requests/{request_id}/reject",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_admin_cannot_approve_another_organization_request(
    client: TestClient,
    authenticated_user: dict,
    authenticated_admin: dict,
):
    owner_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
    other_admin_headers = {"Authorization": f"Bearer {authenticated_admin['token']}"}

    created = client.post(
        "/api/v1/requests",
        headers=owner_headers,
        json={
            "title": "Organization isolation test",
            "description": "Another organization's admin must not approve this.",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["id"]

    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=owner_headers,
    )
    assert submitted.status_code == 200

    response = client.post(
        f"/api/v1/requests/{request_id}/approve",
        headers=other_admin_headers,
    )

    assert response.status_code == 404

    listed = client.get("/api/v1/requests", headers=owner_headers)
    request_data = next(item for item in listed.json() if item["id"] == request_id)
    assert request_data["status"] == "pending"


def test_admin_cannot_decide_request_twice(
    client: TestClient,
    authenticated_user: dict,
    admin_in_same_organization: dict,
):
    owner_headers = {"Authorization": f"Bearer {authenticated_user['token']}"}
    admin_headers = {"Authorization": f"Bearer {admin_in_same_organization['token']}"}

    created = client.post(
        "/api/v1/requests",
        headers=owner_headers,
        json={
            "title": "Single decision test",
            "description": "An approved request must not be rejected afterward.",
        },
    )
    assert created.status_code == 201

    request_id = created.json()["id"]

    submitted = client.post(
        f"/api/v1/requests/{request_id}/submit",
        headers=owner_headers,
    )
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        headers=admin_headers,
    )
    assert approved.status_code == 200

    rejected = client.post(
        f"/api/v1/requests/{request_id}/reject",
        headers=admin_headers,
    )

    assert rejected.status_code == 409

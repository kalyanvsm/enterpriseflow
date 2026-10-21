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

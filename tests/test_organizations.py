import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models import Organization, User

PASSWORD = "StrongPassword1234567890!"


def create_test_user(
    test_session_factory,
    organization_name: str,
    email: str,
) -> tuple[str, str]:
    async def create() -> tuple[str, str]:
        async with test_session_factory() as session:
            organization = Organization(name=organization_name)
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=email.lower(),
                password_hash=hash_password(PASSWORD),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()

            return str(organization.id), create_access_token(str(user.id))

    return asyncio.run(create())


def test_create_organization(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Acme Corporation"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corporation"
    assert "id" in data
    assert "created_at" in data


def test_get_existing_organization(
    client: TestClient,
    test_session_factory,
) -> None:
    organization_id, token = create_test_user(
        test_session_factory,
        "Example Organization",
        "org-reader@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id


def test_get_missing_organization_returns_404(
    client: TestClient,
    test_session_factory,
) -> None:
    _, token = create_test_user(
        test_session_factory,
        "Existing Organization",
        "org-reader@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_create_organization_rejects_too_short_name(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "A"},
    )

    assert response.status_code == 422


def test_create_organization_rejects_missing_name(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/organizations",
        json={},
    )

    assert response.status_code == 422

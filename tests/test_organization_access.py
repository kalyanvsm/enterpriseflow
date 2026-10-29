import asyncio

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.models import Organization, User


def create_organization_and_login(
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
                password_hash=hash_password("StrongPassword1234567890!"),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()

            return str(organization.id), create_access_token(str(user.id))

    return asyncio.run(create())


def test_organization_detail_requires_authentication(
    client: TestClient,
) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Private Organization"},
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]

    response = client.get(f"/api/v1/organizations/{organization_id}")

    assert response.status_code == 401


def test_user_cannot_read_another_organization(
    client: TestClient,
    test_session_factory,
) -> None:
    organization_a_id, token_a = create_organization_and_login(
        test_session_factory,
        "Organization Alpha",
        "alpha@example.com",
    )
    organization_b_id, _ = create_organization_and_login(
        test_session_factory,
        "Organization Beta",
        "beta@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert organization_a_id != organization_b_id
    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


def test_user_can_read_own_organization(
    client: TestClient,
    test_session_factory,
) -> None:
    organization_id, token = create_organization_and_login(
        test_session_factory,
        "My Organization",
        "owner@example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id
    assert response.json()["name"] == "My Organization"

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select

from app.models.user import User


def create_organization(client: TestClient) -> str:
    response = client.post(
        "/api/v1/organizations",
        json={"name": "Test Organization"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_user(client: TestClient) -> None:
    organization_id = create_organization(client)

    response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "alice@example.com",
            "password": "StrongPassowrd1234567890!",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["organization_id"] == organization_id
    assert data["email"] == "alice@example.com"
    assert data["role"] == "employee"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data


def test_create_user_for_missing_organization_returns_404(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "organization_id": str(uuid4()),
            "email": "alice@example.com",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


def test_duplicate_email_in_same_organization_returns_409(
    client: TestClient,
) -> None:
    organization_id = create_organization(client)
    payload = {
        "organization_id": organization_id,
        "email": "alice@example.com",
        "password": "StrongPassword1234567890!",
    }

    first_response = client.post("/api/v1/users", json=payload)
    second_response = client.post("/api/v1/users", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_create_user_rejects_short_password(client: TestClient) -> None:
    organization_id = create_organization(client)

    response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "alice@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_create_user_rejects_invalid_email(client: TestClient) -> None:
    organization_id = create_organization(client)

    response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "not-an-email",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 422


def test_user_password_is_hashed(
    client: TestClient,
    test_session_factory,
) -> None:
    organization_id = create_organization(client)
    password = "StrongPassword1234567890!"

    response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "hashcheck@example.com",
            "password": password,
        },
    )

    assert response.status_code == 201
    assert "password" not in response.json()
    assert "password_hash" not in response.json()

    async def read_stored_hash() -> str:
        async with test_session_factory() as session:
            result = await session.execute(
                select(User.password_hash).where(User.email == "hashcheck@example.com")
            )
            stored_hash = result.scalar_one()
            return stored_hash

    stored_hash = asyncio.run(read_stored_hash())

    assert stored_hash != password
    assert stored_hash.startswith("$argon2")
    assert PasswordHash.recommended().verify(password, stored_hash)

import asyncio

from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select

from app.models.user import User

PASSWORD = "StrongPassword1234567890!"


def admin_headers(create_test_user) -> tuple[dict[str, str], str]:
    admin = create_test_user(role="admin")
    return {"Authorization": f"Bearer {admin['token']}"}, admin["organization_id"]


def test_create_user(
    client: TestClient,
    create_test_user,
) -> None:
    headers, organization_id = admin_headers(create_test_user)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "alice@example.com",
            "password": PASSWORD,
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


def test_create_user_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "email": "alice@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401


def test_employee_cannot_create_user(
    client: TestClient,
    create_test_user,
) -> None:
    employee = create_test_user(role="employee")

    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {employee['token']}"},
        json={
            "email": "new-employee@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 403


def test_admin_cannot_choose_another_organization(
    client: TestClient,
    create_test_user,
) -> None:
    headers, admin_organization_id = admin_headers(create_test_user)
    other_user = create_test_user(role="employee")

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "cross-tenant@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == admin_organization_id
    assert response.json()["organization_id"] != other_user["organization_id"]


def test_create_user_uses_admin_organization(
    client: TestClient,
    create_test_user,
) -> None:
    headers, organization_id = admin_headers(create_test_user)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "admin-org@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == organization_id


def test_duplicate_email_in_same_organization_returns_409(
    client: TestClient,
    create_test_user,
) -> None:
    headers, _ = admin_headers(create_test_user)
    payload = {
        "email": "duplicate@example.com",
        "password": PASSWORD,
    }

    first_response = client.post("/api/v1/users", headers=headers, json=payload)
    second_response = client.post("/api/v1/users", headers=headers, json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_create_user_rejects_short_password(
    client: TestClient,
    create_test_user,
) -> None:
    headers, _ = admin_headers(create_test_user)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "short-password@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_create_user_rejects_invalid_email(
    client: TestClient,
    create_test_user,
) -> None:
    headers, _ = admin_headers(create_test_user)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "not-an-email",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 422


def test_user_password_is_hashed(
    client: TestClient,
    test_session_factory,
    create_test_user,
) -> None:
    headers, _ = admin_headers(create_test_user)
    email = "hashcheck@example.com"

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": email,
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201
    assert "password" not in response.json()
    assert "password_hash" not in response.json()

    async def read_stored_hash() -> str:
        async with test_session_factory() as session:
            result = await session.execute(
                select(User.password_hash).where(User.email == email)
            )
            return result.scalar_one()

    stored_hash = asyncio.run(read_stored_hash())

    assert stored_hash != PASSWORD
    assert stored_hash.startswith("$argon2")
    assert PasswordHash.recommended().verify(PASSWORD, stored_hash)


def test_create_user_rejects_client_supplied_organization_id(
    client: TestClient,
    create_test_user,
) -> None:
    headers, organization_id = admin_headers(create_test_user)

    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "organization_id": organization_id,
            "email": "client-org@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 422

import asyncio
from uuid import UUID

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.user import User


def create_test_user(
    client: TestClient,
    email: str = "alice@example.com",
    password: str = "StrongPassword1234567890!",
) -> str:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Auth Test Organization"},
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": email,
            "password": password,
        },
    )
    assert user_response.status_code == 201
    return user_response.json()["id"]


def test_login_returns_access_token(client: TestClient) -> None:
    user_id = create_test_user(client)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data

    claims = jwt.decode(
        data["access_token"],
        get_settings().jwt_secret_key,
        algorithms=[get_settings().jwt_algorithm],
    )
    assert claims["sub"] == user_id
    assert "exp" in claims


def test_login_rejects_wrong_password(client: TestClient) -> None:
    create_test_user(client)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "WrongPassword1234!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_inactive_user(client: TestClient, test_engine) -> None:
    user_id = create_test_user(client)

    async def deactivate_user() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            await session.execute(
                update(User).where(User.id == UUID(user_id)).values(is_active=False)
            )
            await session.commit()

    asyncio.run(deactivate_user())

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "alice@example.com",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "not-an-email",
            "password": "StrongPassword1234567890!",
        },
    )

    assert response.status_code == 422

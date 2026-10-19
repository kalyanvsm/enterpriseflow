import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.user import User


def test_profile_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401

def test_profile_returns_authenticated_user(client: TestClient) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Profile Test Organization"},
    )
    assert organization_response.status_code == 201

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_response.json()["id"],
            "email": "profile@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201
    created_user = user_response.json()

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "profile@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == created_user["id"]
    assert profile["email"] == "profile@example.com"
    assert profile["organization_id"] == created_user["organization_id"]
    assert "password_hash" not in profile

def test_profile_rejects_malformed_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401

def test_profile_rejects_expired_token(client: TestClient) -> None:
    settings = get_settings()
    expired_token = jwt.encode(
        {
            "sub": "95519f8a-a0c1-4332-bde8-d73a5f1785c1",
            "iat": datetime.now(UTC) - timedelta(minutes=10),
            "exp": datetime.now(UTC) - timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401

def test_profile_rejects_inactive_user(
        client: TestClient,
        test_engine,
) -> None:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": "Inactive User Organization"},
    )
    assert organization_response.status_code == 201

    organization_id = organization_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": "inactive@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201
    user_id = UUID(user_response.json()["id"])

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    async def deactivate_user() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(is_active=False)
            )
            await session.commit()

    asyncio.run(deactivate_user())

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
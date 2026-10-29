import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models import Organization, User

PASSWORD = "StrongPassword1234567890!"


def create_test_user(
    test_session_factory,
    email: str,
) -> tuple[str, str, str]:
    async def create() -> tuple[str, str, str]:
        async with test_session_factory() as session:
            organization = Organization(name=f"Profile Test Organization {uuid4()}")
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

            return (
                str(user.id),
                str(organization.id),
                create_access_token(str(user.id)),
            )

    return asyncio.run(create())


def test_profile_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_profile_returns_authenticated_user(
    client: TestClient,
    test_session_factory,
) -> None:
    user_id, organization_id, token = create_test_user(
        test_session_factory,
        "profile@example.com",
    )

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == user_id
    assert profile["email"] == "profile@example.com"
    assert profile["organization_id"] == organization_id
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
    test_session_factory,
    test_engine,
) -> None:
    user_id, _, token = create_test_user(
        test_session_factory,
        "inactive@example.com",
    )

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

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401

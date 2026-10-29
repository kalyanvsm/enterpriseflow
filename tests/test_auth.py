import asyncio
from uuid import UUID, uuid4

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Organization
from app.models.user import User

PASSWORD = "StrongPassword1234567890!"


def create_test_user(
    test_session_factory,
    email: str = "alice@example.com",
    password: str = PASSWORD,
) -> str:
    async def create() -> str:
        async with test_session_factory() as session:
            organization = Organization(name=f"Auth Test Organization {uuid4()}")
            session.add(organization)
            await session.flush()

            user = User(
                organization_id=organization.id,
                email=email.lower(),
                password_hash=hash_password(password),
                role="employee",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            return str(user.id)

    return asyncio.run(create())


def test_login_returns_access_token(
    client: TestClient,
    test_session_factory,
) -> None:
    user_id = create_test_user(test_session_factory)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": PASSWORD},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data

    settings = get_settings()
    claims = jwt.decode(
        data["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert claims["sub"] == user_id
    assert "exp" in claims


def test_login_rejects_wrong_password(
    client: TestClient,
    test_session_factory,
) -> None:
    create_test_user(test_session_factory)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "WrongPassword1234!"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_inactive_user(
    client: TestClient,
    test_session_factory,
) -> None:
    user_id = create_test_user(test_session_factory)

    async def deactivate_user() -> None:
        async with test_session_factory() as session:
            await session.execute(
                update(User).where(User.id == UUID(user_id)).values(is_active=False)
            )
            await session.commit()

    asyncio.run(deactivate_user())

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "not-an-email",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 422

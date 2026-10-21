from fastapi.testclient import TestClient


def create_user_and_login(
    client: TestClient,
    email: str,
) -> tuple[str, str]:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": f"Organization for {email}"},
    )
    assert organization_response.status_code == 201
    organization_id = organization_response.json()["id"]

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": organization_id,
            "email": email,
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "StrongPassword1234567890!",
        },
    )
    assert login_response.status_code == 200

    return user_response.json()["id"], login_response.json()["access_token"]


def test_admin_endpoint_requires_authentication(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/users/admin-check")

    assert response.status_code == 401


def test_employee_cannot_access_admin_endpoint(
    client: TestClient,
) -> None:
    _, token = create_user_and_login(client, "employee@example.com")

    response = client.get(
        "/api/v1/users/admin-check",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_admin_can_access_admin_endpoint(
    client: TestClient,
    test_engine,
) -> None:
    import asyncio
    from uuid import UUID

    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.user import User

    user_id, token = create_user_and_login(client, "admin@example.com")

    async def promote_user() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            await session.execute(
                update(User).where(User.id == UUID(user_id)).values(role="admin")
            )
            await session.commit()

    asyncio.run(promote_user())

    response = client.get(
        "/api/v1/users/admin-check",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Admin access granted"}

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User
from scripts.promote_admin import promote_user


def create_user(client, email: str) -> tuple[UUID, UUID]:
    organization_response = client.post(
        "/api/v1/organizations",
        json={"name": f"Org for {email}"},
    )
    assert organization_response.status_code == 201
    organization_id = UUID(organization_response.json()["id"])

    user_response = client.post(
        "/api/v1/users",
        json={
            "organization_id": str(organization_id),
            "email": email,
            "password": "StrongPassword1234567890!",
        },
    )
    assert user_response.status_code == 201

    return UUID(user_response.json()["id"]), organization_id


def test_promote_active_user_to_admin(client, test_engine) -> None:
    user_id, organization_id = create_user(client, "promote@example.com")

    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            result = await promote_user(
                session,
                "promote@example.com",
                organization_id,
            )
            assert result is True

            user = await session.get(User, user_id)
            assert user is not None
            assert user.role == "admin"

    asyncio.run(run_test())


def test_promotion_fails_for_missing_user(test_engine) -> None:
    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            result = await promote_user(
                session,
                "missing@example.com",
                UUID("26a91f76-c9f4-4c0d-8250-1cff00100483"),
            )
            assert result is False

    asyncio.run(run_test())


def test_promotion_fails_for_inactive_user(client, test_engine) -> None:
    user_id, organization_id = create_user(client, "inactive-admin@example.com")

    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            await session.execute(select(User).where(User.id == user_id))
            user = await session.get(User, user_id)
            assert user is not None
            user.is_active = False
            await session.commit()

            result = await promote_user(
                session,
                "inactive-admin@example.com",
                organization_id,
            )
            assert result is False
            await session.refresh(user)
            assert user.role == "employee"

    asyncio.run(run_test())

def test_promoting_existing_admin_is_safe(client, test_engine) -> None:
    user_id, organization_id = create_user(client, "existing-admin@example.com")

    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            user = await session.get(User, user_id)
            assert user is not None
            user.role = "admin"
            await session.commit()

            result = await promote_user(
                session,
                "existing-admin@example.com",
                organization_id,
            )

            assert result is True
            await session.refresh(user)
            assert user.role == "admin"

    asyncio.run(run_test())
import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User
from scripts.promote_admin import promote_user


def test_promote_active_user_to_admin(
    create_test_user,
    test_engine,
) -> None:
    user = create_test_user(email="promote@example.com")
    user_id = UUID(user["user_id"])
    organization_id = UUID(user["organization_id"])

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

            promoted_user = await session.get(User, user_id)
            assert promoted_user is not None
            assert promoted_user.role == "admin"

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


def test_promotion_fails_for_inactive_user(
    create_test_user,
    test_engine,
) -> None:
    user = create_test_user(email="inactive-admin@example.com")
    user_id = UUID(user["user_id"])
    organization_id = UUID(user["organization_id"])

    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            user_record = await session.get(User, user_id)
            assert user_record is not None
            user_record.is_active = False
            await session.commit()

            result = await promote_user(
                session,
                "inactive-admin@example.com",
                organization_id,
            )
            assert result is False

            await session.refresh(user_record)
            assert user_record.role == "employee"

    asyncio.run(run_test())


def test_promoting_existing_admin_is_safe(
    create_test_user,
    test_engine,
) -> None:
    user = create_test_user(
        role="admin",
        email="existing-admin@example.com",
    )
    user_id = UUID(user["user_id"])
    organization_id = UUID(user["organization_id"])

    async def run_test() -> None:
        factory = async_sessionmaker(
            test_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with factory() as session:
            result = await promote_user(
                session,
                "existing-admin@example.com",
                organization_id,
            )

            assert result is True
            existing_user = await session.get(User, user_id)
            assert existing_user is not None
            assert existing_user.role == "admin"

    asyncio.run(run_test())

import pytest
from sqlalchemy import func, select

from app.core.security import verify_password
from app.models.organization import Organization
from app.models.user import User
from scripts.bootstrap_admin import (
    bootstrap_admin,
    validate_bootstrap_target,
)


async def count_organizations(test_session_factory) -> int:
    async with test_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(Organization))
        return result.scalar_one()


async def count_users(test_session_factory) -> int:
    async with test_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar_one()


def test_bootstrap_creates_organization_and_admin(test_session_factory) -> None:
    async def run_test() -> None:
        async with test_session_factory() as session:
            organization, admin = await bootstrap_admin(
                session,
                organization_name="Acme Corporation",
                admin_email="OWNER@EXAMPLE.COM",
                admin_password="StrongPassword123!",
            )

            assert organization.name == "Acme Corporation"
            assert admin.organization_id == organization.id
            assert admin.email == "owner@example.com"
            assert admin.role == "admin"
            assert admin.is_active is True
            assert verify_password("StrongPassword123!", admin.password_hash)

    import asyncio

    asyncio.run(run_test())


def test_bootstrap_rejects_existing_email(
    test_session_factory,
    create_test_user,
) -> None:
    existing_user = create_test_user(email="owner@example.com")

    async def run_test() -> None:
        organizations_before = await count_organizations(test_session_factory)

        async with test_session_factory() as session:
            try:
                await bootstrap_admin(
                    session,
                    organization_name="Another Organization",
                    admin_email=existing_user["email"],
                    admin_password="StrongPassword123!",
                )
            except ValueError as exc:
                assert str(exc) == "A user with this email already exists."
            else:
                raise AssertionError("Expected duplicate email to be rejected.")

        organizations_after = await count_organizations(test_session_factory)
        assert organizations_after == organizations_before

    import asyncio

    asyncio.run(run_test())


def test_bootstrap_rolls_back_if_admin_creation_fails(
    test_session_factory,
    monkeypatch,
) -> None:
    import asyncio

    import scripts.bootstrap_admin as bootstrap_module

    def fail_hashing(password: str) -> str:
        raise RuntimeError("Simulated password hashing failure")

    monkeypatch.setattr(bootstrap_module, "hash_password", fail_hashing)

    async def run_test() -> None:
        organizations_before = await count_organizations(test_session_factory)
        users_before = await count_users(test_session_factory)

        async with test_session_factory() as session:
            try:
                await bootstrap_admin(
                    session,
                    organization_name="Rollback Organization",
                    admin_email="rollback@example.com",
                    admin_password="StrongPassword123!",
                )
            except RuntimeError as exc:
                assert str(exc) == "Simulated password hashing failure"
            else:
                raise AssertionError("Expected the simulated failure.")

        assert await count_organizations(test_session_factory) == organizations_before
        assert await count_users(test_session_factory) == users_before

    asyncio.run(run_test())


def test_bootstrap_rejects_blank_organization_name(test_session_factory) -> None:
    import asyncio

    async def run_test() -> None:
        async with test_session_factory() as session:
            try:
                await bootstrap_admin(
                    session,
                    organization_name=" ",
                    admin_email="owner@example.com",
                    admin_password="StrongPassword123!",
                )
            except ValueError as exc:
                assert "Organization name" in str(exc)
            else:
                raise AssertionError("Expected blank organization name to be rejected.")

    asyncio.run(run_test())


def test_bootstrap_rejects_short_password(test_session_factory) -> None:
    import asyncio

    async def run_test() -> None:
        async with test_session_factory() as session:
            try:
                await bootstrap_admin(
                    session,
                    organization_name="Acme Corporation",
                    admin_email="owner@example.com",
                    admin_password="short",
                )
            except ValueError as exc:
                assert "Password" in str(exc)
            else:
                raise AssertionError("Expected short password to be rejected.")

    asyncio.run(run_test())


def test_bootstrap_target_requires_confirmation() -> None:
    with pytest.raises(ValueError, match="confirm-production-bootstrap"):
        validate_bootstrap_target(
            confirmed=False,
            allowed_database="enterpriseflow",
            configured_database="enterpriseflow",
        )


def test_bootstrap_target_requires_database_approval() -> None:
    with pytest.raises(ValueError, match="BOOTSTRAP_ALLOWED_DATABASE"):
        validate_bootstrap_target(
            confirmed=True,
            allowed_database=None,
            configured_database="enterpriseflow",
        )


def test_bootstrap_target_rejects_database_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        validate_bootstrap_target(
            confirmed=True,
            allowed_database="enterpriseflow_test",
            configured_database="enterpriseflow",
        )


def test_bootstrap_target_rejects_unexpected_database() -> None:
    with pytest.raises(ValueError, match="unexpected database"):
        validate_bootstrap_target(
            confirmed=True,
            allowed_database="other_database",
            configured_database="other_database",
        )

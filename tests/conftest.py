import asyncio
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization, User  # noqa: F401
from app.models.audit_log import AuditLog
from app.models.outbox_event import OutboxEvent
from app.models.workflow_request import WorkflowRequest


@pytest.fixture(scope="session")
def test_engine():
    settings = get_settings()

    if settings.test_database_url.database != "enterpriseflow_test":
        raise RuntimeError("Tests must use the dedicated enterpriseflow_test database.")

    engine = create_async_engine(
        settings.test_database_url,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    yield engine

    asyncio.run(engine.dispose())


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database(test_engine) -> Iterator[None]:
    async def setup() -> None:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    yield


@pytest.fixture
def client(test_session_factory) -> Iterator[TestClient]:

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def clean_organizations(test_engine) -> Iterator[None]:
    async def cleanup() -> None:
        async with test_engine.begin() as connection:
            await connection.execute(delete(OutboxEvent))
            await connection.execute(delete(AuditLog))
            await connection.execute(delete(WorkflowRequest))
            await connection.execute(delete(User))
            await connection.execute(delete(Organization))

    asyncio.run(cleanup())
    yield
    asyncio.run(cleanup())


@pytest.fixture
def test_session_factory(test_engine):
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def create_test_user(test_session_factory):
    def create_user(*, role: str = "employee", email: str | None = None):
        actual_email = email or f"{role}-{uuid4()}@example.com"

        async def create() -> dict[str, str]:
            async with test_session_factory() as session:
                organization = Organization(name=f"Test organization {uuid4()}")
                session.add(organization)
                await session.flush()

                user = User(
                    organization_id=organization.id,
                    email=actual_email,
                    password_hash=hash_password("Test-password-123!"),
                    role=role,
                    is_active=True,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

                return {
                    "user_id": str(user.id),
                    "organization_id": str(organization.id),
                    "email": actual_email,
                    "token": create_access_token(str(user.id)),
                }

        return asyncio.run(create())

    return create_user

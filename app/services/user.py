from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User
from app.schemas.user import UserCreate


async def create_user(
    session: AsyncSession,
    user_data: UserCreate,
) -> User:
    organization_result = await session.execute(
        select(Organization).where(Organization.id == user_data.organization_id)
    )
    organization = organization_result.scalar_one_or_none()

    if organization is None:
        raise ValueError("Organization not found")

    user = User(
        organization_id=user_data.organization_id,
        email=str(user_data.email).lower(),
        password_hash=hash_password(user_data.password),
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return user

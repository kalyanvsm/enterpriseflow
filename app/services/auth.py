from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest


async def authenticate_user(
    session: AsyncSession, login_data: LoginRequest
) -> str | None:
    normalized_email = str(login_data.email).lower()

    result = await session.execute(
        select(User).where(
            User.email == normalized_email,
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None

    if not verify_password(login_data.password, user.password_hash):
        return None

    return create_access_token(str(user.id))

from uuid import UUID

from fastapi import Depends, Request
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


class UIAuthenticationError(Exception):
    """Raised when a UI request is not authenticated."""


async def get_current_ui_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()

    if not token:
        raise UIAuthenticationError()

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise UIAuthenticationError()
        user_id = UUID(subject)
    except (InvalidTokenError, ValueError):
        raise UIAuthenticationError() from None

    result = await session.execute(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise UIAuthenticationError()

    return user


async def get_optional_ui_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User | None:
    try:
        return await get_current_ui_user(request, session)
    except UIAuthenticationError:
        return None

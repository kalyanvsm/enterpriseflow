from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserProfileResponse, UserResponse
from app.services.user import create_user

router = APIRouter(
    prefix="/users",
    tags=["users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_endpoint(
    user_data: UserCreate,
    current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:

    try:
        return await create_user(
            session,
            user_data,
            organization_id=current_user.organization_id,
        )
    except ValueError as exc:
        if str(exc) == "Organization not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            ) from exc
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists in this organization.",
        ) from exc


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    return current_user


@router.get("/admin-check")
async def admin_check(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    return {"message": "Admin access granted"}

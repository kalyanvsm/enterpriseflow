from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.organization import OrganizationCreate, OrganizationResponse
from app.services.organization import create_organization, get_organization

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_endpoint(
    organization_data: OrganizationCreate,
    session: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    return await create_organization(session, organization_data)


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
async def get_organization_endpoint(
    organization_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> OrganizationResponse:
    organization = await get_organization(session, organization_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return organization

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.schemas.organization import OrganizationCreate


async def create_organization(
    session: AsyncSession, organization_data: OrganizationCreate
) -> Organization:
    organization = Organization(name=organization_data.name)
    session.add(organization)

    await session.commit()
    await session.refresh(organization)

    return organization


async def get_organization(
    session: AsyncSession,
    organization_id,
) -> Organization | None:
    result = await session.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    return result.scalar_one_or_none()

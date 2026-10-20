import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.user import User


async def promote_user(
    session: AsyncSession,
    email: str,
    organization_id: UUID,
) -> bool:
    result = await session.execute(
        select(User).where(
            User.email == email.lower(),
            User.organization_id == organization_id,
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        print("No matching user found. No changes made.")
        return False

    if not user.is_active:
        print("The matching user is inactive. No changes made.")
        return False

    if user.role == "admin":
        print("This user is already an admin. No changes made.")
        return True

    user.role = "admin"
    await session.commit()

    print(f"Promoted {user.email} to admin.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote an existing active user to admin."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--organization-id", required=True, type=UUID)
    args = parser.parse_args()

    print("WARNING: This command modifies the application database.")
    print(f"User email: {args.email}")
    print(f"Organization ID: {args.organization_id}")
    confirmation = input("Type PROMOTE to continue: ")

    if confirmation != "PROMOTE":
        print("Cancelled. No changes made.")
        return

    async def run_promotion() -> None:
        async with SessionLocal() as session:
            await promote_user(session, args.email, args.organization_id)

    asyncio.run(run_promotion())


if __name__ == "__main__":
    main()

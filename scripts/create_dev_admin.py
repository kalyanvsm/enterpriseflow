import asyncio
import getpass

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.user import User


async def main():
    email = input("Development admin email: ").strip().lower()
    password = getpass.getpass("Development admin password (min 8 characters): ")
    confirmation = getpass.getpass("Confirm password: ")

    if not email or "@" not in email:
        raise SystemExit("Please enter a valid email address.")
    if not 8 <= len(password) <= 128:
        raise SystemExit("Password must be between 8 and 128 characters.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    async with SessionLocal() as session:
        async with session.begin():
            org_count = await session.scalar(
                select(func.count()).select_from(Organization)
            )
            user_count = await session.scalar(
                select(func.count()).select_from(User)
            )

            if org_count or user_count:
                raise SystemExit(
                    "Database is not empty. No records were created."
                )

            organization = Organization(name="EnterpriseFlow Development")
            session.add(organization)
            await session.flush()

            admin = User(
                organization_id=organization.id,
                email=email,
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
            session.add(admin)

    print("Development organization and admin created successfully.")
    print(f"Admin email: {email}")
    print("Password: not displayed")


if __name__ == "__main__":
    asyncio.run(main())

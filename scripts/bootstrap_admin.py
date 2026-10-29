import argparse
import asyncio
import os
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.user import User

email_adapter = TypeAdapter(EmailStr)


async def bootstrap_admin(
    session: AsyncSession,
    *,
    organization_name: str,
    admin_email: str,
    admin_password: str,
) -> tuple[Organization, User]:
    normalized_name = organization_name.strip()
    normalized_email = admin_email.strip().lower()

    if not 2 <= len(normalized_name) <= 150:
        raise ValueError("Organization name must be between 2 and 150 characters.")

    if not 8 <= len(admin_password) <= 128:
        raise ValueError("Password must be between 8 and 128 characters.")

    try:
        normalized_email = str(email_adapter.validate_python(normalized_email))
    except ValidationError as exc:
        raise ValueError("A valid admin email is required.") from exc

    existing_user = await session.execute(
        select(User.id).where(User.email == normalized_email)
    )
    if existing_user.scalar_one_or_none() is not None:
        raise ValueError("A user with this email already exists.")

    organization = Organization(name=normalized_name)
    session.add(organization)

    try:
        await session.flush()

        admin = User(
            organization_id=organization.id,
            email=normalized_email,
            password_hash=hash_password(admin_password),
            role="admin",
            is_active=True,
        )
        session.add(admin)

        await session.commit()
        await session.refresh(organization)
        await session.refresh(admin)
        return organization, admin
    except Exception:
        await session.rollback()
        raise


def validate_bootstrap_target(
    *,
    confirmed: bool,
    allowed_database: str | None,
    configured_database: str | None,
) -> None:
    if not confirmed:
        raise ValueError("Refusing to run without --confirm-production-bootstrap.")

    if not allowed_database:
        raise ValueError(
            "Set BOOTSTRAP_ALLOWED_DATABASE to the intended database name."
        )

    if allowed_database != configured_database:
        raise ValueError(
            "BOOTSTRAP_ALLOWED_DATABASE does not match the configured database."
        )

    if configured_database != "enterpriseflow":
        raise ValueError("Refusing to bootstrap against an unexpected database.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an organization and its initial admin user."
    )
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument(
        "--confirm-production-bootstrap",
        action="store_true",
        help="Explicitly acknowledge that this command creates an admin.",
    )
    args = parser.parse_args()

    settings = get_settings()

    try:
        validate_bootstrap_target(
            confirmed=args.confirm_production_bootstrap,
            allowed_database=os.getenv("BOOTSTRAP_ALLOWED_DATABASE"),
            configured_database=settings.database_url.database,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print("\nInitial admin setup")
    print(f"Organization: {args.organization_name}")
    print(f"Admin email:  {args.admin_email}")
    confirmation = input('\nType "CREATE" to continue: ')

    if confirmation != "CREATE":
        print("Setup cancelled.")
        return

    password = getpass("Admin password (8–128 characters): ")
    password_confirmation = getpass("Confirm admin password: ")

    if password != password_confirmation:
        print("Passwords do not match.")
        return

    async def run() -> None:
        async with SessionLocal() as session:
            try:
                organization, admin = await bootstrap_admin(
                    session,
                    organization_name=args.organization_name,
                    admin_email=args.admin_email,
                    admin_password=password,
                )
            except ValueError as exc:
                print(f"Setup rejected: {exc}")
                return
            except IntegrityError:
                print(
                    "Setup failed because of a database constraint. "
                    "No changes were committed."
                )
                return

            print("\nInitial admin created successfully.")
            print(f"Organization ID: {organization.id}")
            print(f"Admin user ID:   {admin.id}")
            print(f"Admin email:     {admin.email}")

    asyncio.run(run())


if __name__ == "__main__":
    main()

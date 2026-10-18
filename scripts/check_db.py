import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT current_database(), current_user")
        )
        database, user = result.one()

    print(f"Database connection successful: {database} as user {user}")


if __name__ == "__main__":
    asyncio.run(main())

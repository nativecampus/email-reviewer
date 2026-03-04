"""Drop all tables and re-apply migrations from scratch.

Connects to the database specified by DATABASE_URL, drops every table managed
by the ORM, then runs ``alembic upgrade head`` to recreate the schema.

Usage:
    python -m scripts.db_reset          # prompts for confirmation
    python -m scripts.db_reset --yes    # skip confirmation
"""

import argparse
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _build_engine():
    import re

    from app.config import settings

    url = settings.DATABASE_URL
    # Ensure async driver for PostgreSQL URLs.
    url = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)
    return create_async_engine(url)


async def _drop_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def _run_migrations():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
    )
    if result.returncode != 0:
        print("Migration failed.", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Drop all tables and re-apply migrations.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    args = parser.parse_args()

    if not args.yes:
        answer = input("This will destroy all data. Continue? [y/N] ")
        if answer.strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)

    import asyncio

    engine = _build_engine()
    print("Dropping all tables...")
    asyncio.run(_drop_tables(engine))

    print("Running migrations...")
    _run_migrations()

    print("Database reset complete.")


if __name__ == "__main__":
    main()

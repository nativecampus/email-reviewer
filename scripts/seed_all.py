"""Populate the database with seed data.

Inserts reps, emails, and scores in dependency order. Idempotent - skips
records that already exist (matched by primary key or hubspot_id).

Usage:
    python -m scripts.seed_all
"""

import asyncio
import re
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Email, Rep, Score  # noqa: F401 - registers tables
from scripts.seeds.emails import EMAILS
from scripts.seeds.reps import REPS
from scripts.seeds.scores import SCORES


def _build_engine():
    url = settings.DATABASE_URL
    url = re.sub(r"^postgresql(\+\w+)?://", "postgresql+asyncpg://", url)
    return create_async_engine(url)


async def _seed_reps(session: AsyncSession):
    inserted = 0
    for data in REPS:
        existing = await session.get(Rep, data["email"])
        if existing:
            continue
        session.add(Rep(**data))
        inserted += 1
    await session.flush()
    print(f"  reps: {inserted} inserted, {len(REPS) - inserted} already present")


async def _seed_emails(session: AsyncSession):
    inserted = 0
    for data in EMAILS:
        result = await session.execute(
            select(Email).where(Email.hubspot_id == data["hubspot_id"])
        )
        if result.scalar_one_or_none():
            continue
        session.add(Email(**data))
        inserted += 1
    await session.flush()
    print(f"  emails: {inserted} inserted, {len(EMAILS) - inserted} already present")


async def _seed_scores(session: AsyncSession):
    inserted = 0
    for data in SCORES:
        hubspot_id = data.pop("hubspot_id")
        result = await session.execute(
            select(Email).where(Email.hubspot_id == hubspot_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            print(f"  scores: skipping - no email with hubspot_id {hubspot_id}")
            data["hubspot_id"] = hubspot_id
            continue

        existing = await session.execute(
            select(Score).where(Score.email_id == email.id)
        )
        if existing.scalar_one_or_none():
            data["hubspot_id"] = hubspot_id
            continue

        session.add(Score(email_id=email.id, **data))
        inserted += 1
        data["hubspot_id"] = hubspot_id
    await session.flush()
    print(f"  scores: {inserted} inserted, {len(SCORES) - inserted} already present")


async def _run():
    engine = _build_engine()
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            print("Seeding database...")
            await _seed_reps(session)
            await _seed_emails(session)
            await _seed_scores(session)
            print("Done.")

    await engine.dispose()


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()

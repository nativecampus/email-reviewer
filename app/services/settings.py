from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import Settings
from app.schemas.settings import SettingsUpdate


async def get_settings(session: AsyncSession) -> Settings:
    """Return the single settings row, creating it with defaults if missing."""
    result = await session.execute(select(Settings).where(Settings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = Settings(id=1)
        session.add(row)
        await session.flush()
    return row


async def update_settings(
    session: AsyncSession, updates: SettingsUpdate
) -> Settings:
    """Apply partial updates to the settings row and return it."""
    settings = await get_settings(session)
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    await session.flush()
    await session.refresh(settings)
    return settings

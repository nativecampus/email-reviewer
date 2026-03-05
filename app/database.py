from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _async_database_url(url: str) -> str:
    """Convert a database URL to use an async driver."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(_async_database_url(settings.DATABASE_URL))
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLocal = async_session


async def get_db():
    async with async_session() as session:
        yield session

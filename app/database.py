from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _async_database_url(url: str) -> str:
    """Convert a database URL to use an async driver."""
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _create_engine(url: str):
    """Create an async engine with appropriate settings for the driver."""
    kwargs: dict = {}
    if url.startswith("postgresql"):
        kwargs["pool_timeout"] = 10
        kwargs["connect_args"] = {"timeout": 10}
    return create_async_engine(url, **kwargs)


_url = _async_database_url(settings.DATABASE_URL)
engine = _create_engine(_url)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLocal = async_session


async def get_db():
    async with async_session() as session:
        yield session


@asynccontextmanager
async def worker_session():
    """Create a fresh engine and session for use in RQ worker processes.

    RQ tasks call asyncio.run() which creates a new event loop. The module-level
    engine was created at import time and its asyncpg connection pool is bound to
    a different loop. This factory creates a new engine within the current loop,
    yields a session, then disposes the engine.
    """
    worker_engine = _create_engine(_url)
    factory = async_sessionmaker(worker_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await worker_engine.dispose()

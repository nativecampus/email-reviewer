import pytest
from sqlalchemy import JSON, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.base import Base

# ---------------------------------------------------------------------------
# SQLite compatibility: compile JSONB as JSON so PostgreSQL-specific column
# types work transparently in the in-memory test database.
# ---------------------------------------------------------------------------
try:
    from sqlalchemy.dialects.postgresql import JSONB

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
        return "JSON"

except ImportError:
    pass

# ---------------------------------------------------------------------------
# In-memory async SQLite engine shared across a single test via StaticPool.
# ---------------------------------------------------------------------------
test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _setup_db():
    """Create all tables before each test, drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def db():
    """Yield an AsyncSession that rolls back on teardown."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture()
async def client(db):
    """httpx.AsyncClient wired to the FastAPI app with the test database."""
    import httpx

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Factory fixtures (stubs) - will be fleshed out as models are built.
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_rep(db):
    async def _make(**overrides):
        raise NotImplementedError("Rep model not yet defined")

    return _make


@pytest.fixture()
def make_email(db):
    async def _make(**overrides):
        raise NotImplementedError("Email model not yet defined")

    return _make


@pytest.fixture()
def make_score(db):
    async def _make(**overrides):
        raise NotImplementedError("Score model not yet defined")

    return _make

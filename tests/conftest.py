import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import ChainScore, Email, EmailChain, Job, Rep, Score, Settings  # noqa: F401 — registers tables
from app.models.base import Base
from tests.fixtures.hubspot import make_hubspot_email, make_hubspot_response


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


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


@pytest.fixture(autouse=True)
async def _setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed default settings row so every test has settings available
    async with TestingSessionLocal() as session:
        settings_row = Settings(id=1)
        session.add(settings_row)
        await session.commit()
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def db():
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture()
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture()
def make_rep(db):
    async def _make(**overrides):
        defaults = {
            "email": "alice@example.com",
            "display_name": "Alice Example",
        }
        defaults.update(overrides)
        rep = Rep(**defaults)
        db.add(rep)
        await db.flush()
        return rep

    return _make


@pytest.fixture()
def make_email(db):
    async def _make(**overrides):
        defaults = {
            "from_email": "rep@example.com",
            "subject": "Hello",
            "body_text": "Test body",
        }
        defaults.update(overrides)
        email = Email(**defaults)
        db.add(email)
        await db.flush()
        return email

    return _make


@pytest.fixture()
def make_score(db):
    async def _make(**overrides):
        defaults = {
            "personalisation": 7,
            "clarity": 8,
            "value_proposition": 6,
            "cta": 7,
            "overall": 7,
            "notes": "Good email",
        }
        defaults.update(overrides)
        score = Score(**defaults)
        db.add(score)
        await db.flush()
        return score

    return _make


@pytest.fixture()
def make_settings(db):
    async def _make(**overrides):
        from sqlalchemy import select as sa_select, update

        if overrides:
            stmt = update(Settings).where(Settings.id == 1).values(**overrides)
            await db.execute(stmt)
            await db.flush()
        result = await db.execute(sa_select(Settings).where(Settings.id == 1))
        return result.scalar_one()

    return _make


@pytest.fixture()
def make_job(db):
    async def _make(**overrides):
        defaults = {
            "job_type": "FETCH",
            "status": "PENDING",
            "triggered_by": "ui",
        }
        defaults.update(overrides)
        job = Job(**defaults)
        db.add(job)
        await db.flush()
        return job

    return _make


@pytest.fixture()
def make_chain(db):
    async def _make(**overrides):
        defaults = {
            "normalized_subject": "Test Subject",
            "participants": "alice@example.com,bob@example.com",
            "email_count": 2,
            "outgoing_count": 1,
            "incoming_count": 1,
        }
        defaults.update(overrides)
        chain = EmailChain(**defaults)
        db.add(chain)
        await db.flush()
        return chain

    return _make


@pytest.fixture()
def make_chain_score(db, make_chain):
    async def _make(**overrides):
        if "chain_id" not in overrides:
            chain = await make_chain()
            overrides["chain_id"] = chain.id
        defaults = {
            "progression": 7,
            "responsiveness": 8,
            "persistence": 6,
            "conversation_quality": 7,
        }
        defaults.update(overrides)
        chain_score = ChainScore(**defaults)
        db.add(chain_score)
        await db.flush()
        return chain_score

    return _make


@pytest.fixture()
def hubspot_email_factory():
    """Factory that builds individual HubSpot API email result objects."""
    return make_hubspot_email


@pytest.fixture()
def hubspot_response_factory():
    """Factory that wraps email results in the HubSpot search API envelope."""
    return make_hubspot_response

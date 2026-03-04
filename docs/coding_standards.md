# Coding Agent Standards

This document defines the patterns, practices, and rules to follow when building applications. Follow it exactly.

---

## CLAUDE.md

Every project must have a `CLAUDE.md` at the root. It must contain:

1. **Testing** - a pointer to the testing guide with an instruction to read it before writing or modifying any test.
2. **Documentation** - a statement that when making a change that affects documented behaviour (new endpoints, model changes, config changes, enum additions, migration additions), the relevant docs must be updated. When adding a new feature, review the existing documentation in its entirety rather than just appending a new section. Other parts of the docs may reference the area you changed and need updating to stay accurate.
3. **Style** - no meta commentary in code comments, commit messages, or documentation. State what the code does or why a decision was made. Do not narrate the act of writing it, explain that you made a change, or add filler like "This is a simple function that..." or "Updated to reflect the new...".

---

## Architecture

### Layered Structure

```
enums  →  models  →  schemas  →  services  →  routers
```

| Layer | Role |
|-------|------|
| Enums | All `(str, Enum)` definitions shared by models and schemas. Serialise as plain strings in the database and JSON. Single file. |
| Models | ORM layer. One file per domain. All inherit a common audit mixin and declarative base. |
| Schemas | Pydantic. Three schemas per entity: `Create`, `Update`, `Response`. One file per domain. |
| Services | Business logic. Pure functions where possible. Separated from routers. |
| Routers | HTTP endpoints. HTML views (excluded from OpenAPI schema) and JSON API. |

Dependencies flow strictly left to right. Routers depend on schemas and services. Services depend on models. Schemas depend on enums. Models depend on enums and base.

### Project Structure

```
project/
├── app/
│   ├── main.py            # App entry point, mounts routers and static files
│   ├── config.py           # pydantic-settings configuration
│   ├── database.py         # Engine + session factory + get_db dependency
│   ├── enums.py            # All enum definitions
│   ├── models/             # ORM models (one file per domain + base.py)
│   ├── routers/            # Route handlers
│   ├── schemas/            # Pydantic schemas (one file per domain + base.py)
│   ├── services/           # Business logic
│   ├── static/             # CSS, images
│   └── templates/          # Jinja2 templates
├── alembic/                # Migration scripts
├── docs/                   # Project documentation
├── scripts/                # Utility and seed scripts
├── tests/                  # Test suite
├── Pipfile / Pipfile.lock
├── Procfile
├── pytest.ini
├── alembic.ini
└── CLAUDE.md
```

---

## Enums

All enums use `(str, Enum)` so values serialise as plain strings in both the database and JSON responses. Define all enums in a single `app/enums.py` file. Group by domain with section comments.

```python
from enum import Enum

class Status(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
```

---

## Models

### Base and Audit Mixin

Define a `Base` (SQLAlchemy `DeclarativeBase`) and an `AuditMixin` in `app/models/base.py`. The mixin adds four columns to every entity:

| Column | Type | Behaviour |
|--------|------|-----------|
| `created_at` | DateTime | Server default `now()` |
| `updated_at` | DateTime | Server default `now()`, auto-updated via `onupdate` |
| `created_by` | String | Set by ORM `before_insert` event |
| `updated_by` | String | Set by ORM `before_insert` and `before_update` events |

ORM event listeners are registered automatically for every `AuditMixin` subclass via `__init_subclass__`. Routers never set `created_by` or `updated_by` directly.

User identity is resolved by a `get_current_user()` function gated by an environment variable for auth. When auth is disabled (local dev/test), it reads a username from an env var. When enabled, it resolves from the authenticated request context.

### Domain Models

One file per domain. Every model inherits both `AuditMixin` and `Base`. Use explicit `Column` definitions. Define relationships with `relationship()`.

```python
from app.models.base import AuditMixin, Base

class Entity(AuditMixin, Base):
    __tablename__ = "entity"
    entity_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    # ...
```

### Model Registration

Import all model modules in `app/models/__init__.py` so `Base.metadata` knows every table. This is required for Alembic autogenerate and for `create_all` in tests.

```python
from app.models.base import Base  # noqa: F401
import app.models.domain_a  # noqa: F401
import app.models.domain_b  # noqa: F401
```

---

## Schemas

### Base Schema

Define a `SIDPBase` (or project-equivalent) in `app/schemas/base.py` with `ConfigDict(from_attributes=True)`.

```python
from pydantic import BaseModel, ConfigDict

class ProjectBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

### Three Schemas Per Entity

For every entity, define three schemas in the domain's schema file:

1. **`{Entity}Create`** - POST body. Required fields mandatory, nullable fields `Optional`.
2. **`{Entity}Update`** - PATCH body. All fields `Optional` for partial updates.
3. **`{Entity}Response`** - Extends Create with primary key and audit fields (`created_at`, `updated_at`, `created_by`, `updated_by`).

```python
class EntityCreate(ProjectBase):
    name: str
    description: str | None = None

class EntityUpdate(ProjectBase):
    name: str | None = None
    description: str | None = None

class EntityResponse(EntityCreate):
    entity_id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
```

### Custom Validators

Test custom validators only. Use `@model_validator` for cross-field validation on Create schemas. Use `@field_validator` for individual field format checks on Update schemas.

If the Response schema inherits from Create and the Create has a `@model_validator`, override it in Response to be a no-op if the validation rules don't apply to database-sourced data.

---

## Routers

### Router Pattern

Each router file follows this structure:

1. HTML views (marked `include_in_schema=False`) - server-rendered templates
2. JSON API endpoints - standard REST with Pydantic request/response models

### HTML Views

HTML endpoints return `TemplateResponse` with shared navigation context. They support search, filtering, and sorting via query parameters. They are excluded from the OpenAPI schema.

### JSON API Endpoints

Follow `/{prefix}/api/...` for list/create and `/{prefix}/api/{id}` for get/update/delete.

| Verb | Path | Purpose | Status Code |
|------|------|---------|-------------|
| GET | `/api/list` | List all (with optional filters) | 200 |
| POST | `/api` | Create | 201 |
| GET | `/api/{id}` | Get one | 200 / 404 |
| PATCH | `/api/{id}` | Partial update | 200 / 404 |
| DELETE | `/api/{id}` | Delete | 200 / 404 |

### Partial Updates (PATCH)

Use `model_dump(exclude_unset=True)` on the Pydantic Update schema to apply only the fields the client sent.

```python
for field, value in payload.model_dump(exclude_unset=True).items():
    setattr(entity, field, value)
db.commit()
```

### Error Handling

Return `HTTPException` with appropriate status codes:
- `404` for not found
- `409` for uniqueness conflicts
- `422` for validation failures (Pydantic handles this automatically)

---

## Configuration

Use `pydantic-settings` in `app/config.py`. Read from environment or `.env` file. Instantiate a singleton `settings` object at module level.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Project"
    DATABASE_URL: str = "postgresql://localhost:5432/db"
    DEBUG: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Database

`app/database.py` creates the engine and session factory from `DATABASE_URL`. `get_db()` is a FastAPI dependency that yields a session and closes it on completion.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## Migrations

Managed with Alembic. Connection string read from the environment in `alembic/env.py`. The Alembic env file imports `Base` from models to access `target_metadata`.

```bash
# Generate a migration from model changes
alembic revision --autogenerate -m "description"

# Apply pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## Services

Business logic lives in `app/services/`, separated from routers. Services should be pure functions where possible - take config/input objects, return results. This makes them testable without HTTP or database dependencies.

```python
def calculate_result(config, inputs) -> dict:
    """Pure function. No database access. No side effects."""
    # ...
    return {"result": value}
```

When database access is required (lookups, aggregation), accept a `Session` parameter explicitly rather than importing the global session.

---

## Testing

### What to Test

- Behaviour, not implementation. If a pure refactor breaks your tests, the tests are coupled to implementation.
- Public interfaces. Inputs in, expected outputs out.
- Edge cases in your logic. Nulls, empty collections, boundary values - but only where your code makes decisions about them.
- State transitions and their guards.
- Error paths. Right exception, right fallback. Assert meaningful content in messages, not full string equality.
- Conditional rendering. If a component decides whether to show something based on state or props, that's logic.
- User interaction flows. Click, submit, display. Test what the user experiences.
- Derived display state. Formatting, computed values, status selection. Extract into pure functions where possible and test those.

### What Not to Test

- Framework and library code. You didn't write it.
- Private methods directly. They get covered through the public interface.
- Implementation details. Don't assert which internal methods were called or how data is structured internally.
- Trivial code. Getters, setters, pass-through assignments, constructors with no logic.
- External systems in unit tests. Mock the boundary. Integration tests are separate.
- Static markup. If nothing in your code decides whether or what to render, there's nothing to test.
- Styling and layout. Unit tests are the wrong tool. Use screenshot comparison for visual regression coverage.
- Component composition. Don't test that Parent renders Child. Test what the user sees.
- Snapshots as a default. They pass on first run, break on every change, and get bulk-updated without review. Exception: tightly scoped snapshots for stable contracts like API schemas are legitimate.

### Stack-Specific Guidance

**Web framework routes:** Use a test client. Test status codes, response shapes, and auth guards. Don't test that the framework parses JSON - it does.

**Pydantic models:** Test custom validators only. Don't test that a field with `str` rejects an `int` - Pydantic handles that.

**SQLAlchemy:** Integration-test your query logic - filters, joins, aggregations - against a real test database. Don't mock the ORM session.

**Alembic migrations:** Test that upgrade then downgrade is reversible and that data survives the round trip.

**Templates:** Test that your route passes the right context to the template. Asserting key content in rendered output is fine - don't test static markup or visual detail.

**Dependency injection:** Override dependencies in tests using the framework's override mechanism. Don't mock framework internals.

**Configuration:** Don't test config loading. Set env vars in your test fixtures and move on.

### Test Infrastructure

#### Database

Tests use in-memory SQLite (not PostgreSQL). Tables are created before each test and dropped after. This gives test isolation without the cost of a real database.

If the production database uses PostgreSQL-specific types (e.g. `JSONB`), register a SQLAlchemy compiler extension to compile them as their SQLite equivalents (e.g. `JSON`).

Enable foreign key enforcement in SQLite via `PRAGMA foreign_keys=ON` on each connection.

Use `StaticPool` so all threads share one connection (required for in-memory SQLite with multithreaded test clients).

```python
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

#### Fixtures

Define fixtures in `tests/conftest.py`:

| Fixture | Description |
|---------|-------------|
| `_setup_db` | Autouse. Creates all tables before each test, drops after. |
| `db` | Yields a SQLAlchemy session. Rolls back on teardown. |
| `client` | Test client wired to the test database via `dependency_overrides`. |
| `make_{entity}()` | Factory fixtures. Create entities with sensible defaults. Accept keyword overrides. Handle foreign key dependencies by creating parent entities automatically if not provided. |

Factory fixtures follow this pattern:

```python
@pytest.fixture()
def make_entity(db):
    def _make(*, name="Default Name", status=Status.ACTIVE, **overrides):
        entity = Entity(
            name=name,
            status=status,
            created_by="test",
            updated_by="test",
            **overrides,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return entity
    return _make
```

Key properties of factory fixtures:
- Use keyword-only arguments for all parameters.
- Provide sensible defaults so tests only specify what they care about.
- Accept `**overrides` for any additional fields.
- Always set audit fields to `"test"`.
- Commit and refresh so the returned entity has its generated primary key.
- When the entity has a foreign key dependency, accept an optional parent parameter. If not provided, create one using the parent's factory fixture.

#### Test Client

The test client overrides the `get_db` dependency to use the test session. Clear overrides after each test.

```python
@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

#### Pytest Configuration

```ini
[pytest]
testpaths = tests
addopts = --maxfail=3 --disable-warnings -q --cov=app --cov-report=term --cov-fail-under=80
env =
    AUTH_ENABLED=FALSE
    CURRENT_USER=test
```

- `testpaths = tests` restricts collection to the `tests/` directory so utility scripts are never picked up.
- 80% coverage minimum is enforced.
- `--maxfail=3` stops after 3 failures.
- Test environment variables are managed by `pytest-env` and override any `.env` values for determinism.

### Test Organisation

Organise tests by what they test:

| File Pattern | Scope |
|--------------|-------|
| `test_main.py` | Health and readiness endpoints |
| `test_audit.py` | Audit user resolution and ORM audit events |
| `test_{entity}_router.py` | HTML views + JSON API for that entity |
| `test_{entity}.py` | Schema validation (custom validators only) |
| `test_models.py` | Schema registration, table presence, column checks |
| `test_enums.py` | Enum value validation |
| `test_views.py` | Navigation and landing page |
| `test_{service}.py` | Business logic / calculation tests |

### Test Style

- Group related tests in classes.
- Name test classes after the thing being tested: `TestContactsAPI`, `TestContactDetailPage`.
- Name test methods descriptively: `test_list_page_search_filters_by_name`, `test_api_create_contact_missing_required_field`.
- Each test sets up its own data using factory fixtures. No shared state between tests.
- Assert status codes, response shapes, and meaningful content. Don't assert full response bodies.
- For HTML view tests, assert that key content appears in `resp.text`. Don't test static markup.
- For API tests, assert status code, then check specific fields in `resp.json()`.

```python
class TestEntityAPI:
    def test_create(self, client):
        resp = client.post("/entity/api", json={"name": "Test"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test"
        assert resp.json()["entity_id"] is not None

    def test_create_missing_required_field(self, client):
        resp = client.post("/entity/api", json={})
        assert resp.status_code == 422

    def test_get_404(self, client):
        resp = client.get("/entity/api/99999")
        assert resp.status_code == 404

    def test_update_partial(self, client, make_entity):
        entity = make_entity(name="Original")
        resp = client.patch(f"/entity/api/{entity.entity_id}", json={"name": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
```

### Visual Testing

Visual tests use a browser automation tool (Selenium/Playwright) to capture screenshots in a headless browser. They live in `scripts/` (not `tests/`) because they require browser dependencies not available in CI.

Visual test setup:
1. Create an in-memory SQLite database with the same compatibility patches as the test suite.
2. Insert seed data via ORM.
3. Override `get_db` on the app and start the server in a daemon thread.
4. Launch a headless browser, navigate to each page, resize viewport to full page height, capture screenshot.
5. Save screenshots as PNG files.

---

## Seed Data

Seed scripts live in `scripts/`. All scripts are idempotent - they check for existing records and skip if present. A single `seed_all.py` runs all seed scripts in dependency order.

A reset script drops all tables and re-applies migrations from scratch. It accepts a `--yes` flag to skip confirmation.

---

## CI/CD

Pipeline:
1. Spin up a PostgreSQL service container.
2. Set up the correct Python version.
3. Install dependencies.
4. Run migrations (`alembic upgrade head`).
5. Run tests (`pytest`).

---

## Documentation

The project manual lives in `docs/`. Maintain the following documents:

| Document | Contents |
|----------|----------|
| `architecture.md` | Layered structure, configuration, database, audit trail, schema/router patterns, navigation, templates, static assets |
| `data-model.md` | All models, columns, types, constraints, relationships, ER summary |
| `api-reference.md` | Every endpoint: method, path, parameters, request/response bodies, error codes |
| `development.md` | Prerequisites, local setup, seeding, running server, running tests, fixture reference, test file organisation, migrations, CI/CD, deployment, project structure |
| `testing-guide.md` | What to test, what not to test, stack-specific guidance |

When a change affects documented behaviour, update the relevant docs. Review existing documentation in its entirety when adding a new feature - other sections may reference the area you changed.

---

## Style Rules

- No meta commentary in code comments, commit messages, or documentation.
- State what the code does or why a decision was made.
- Do not narrate the act of writing it.
- Do not add filler like "This is a simple function that..." or "Updated to reflect the new...".
- No em-dashes in code or documentation. Use single hyphens for parenthetical dashes.

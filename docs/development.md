# Development

## Prerequisites

- Python 3.12
- [pipenv](https://pipenv.pypa.io/)
- PostgreSQL 16 (local or remote)

## Local Setup

1. Clone the repository and install dependencies:

```bash
git clone <repo-url>
cd email-reviewer
pipenv install --dev
```

2. Copy the example environment file and fill in credentials:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://user:pass@localhost:5432/email_reviewer` |
| `HUBSPOT_ACCESS_TOKEN` | HubSpot private app access token |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude scoring |
| `AUTH_ENABLED` | Set to `FALSE` for local development |
| `CURRENT_USER` | Username recorded in audit columns (e.g. your name) |

3. Create the database and run migrations:

```bash
createdb email_reviewer
pipenv run alembic upgrade head
```

## Seeding and Resetting the Database

**Reset** drops all tables and re-applies migrations from scratch:

```bash
pipenv run python -m scripts.db_reset          # prompts for confirmation
pipenv run python -m scripts.db_reset --yes    # skip confirmation
```

**Seed** populates the database with sample reps, emails, and scores. Idempotent - skips records that already exist:

```bash
pipenv run python -m scripts.seed_all
```

To start fresh with seed data:

```bash
pipenv run python -m scripts.db_reset --yes && pipenv run python -m scripts.seed_all
```

Seed data files live in `scripts/seeds/`:

| File | Contents |
|------|----------|
| `reps.py` | Sales rep email addresses and display names |
| `emails.py` | Sample outgoing sales emails (derived from HubSpot fixtures) |
| `scores.py` | Sample Claude API scoring results for the seed emails |

## Running the Server

```bash
pipenv run uvicorn app.main:app --reload --port 8000
```

The `--reload` flag enables auto-restart on file changes. The app is available at `http://localhost:8000`. Dashboard at `/`, settings and operations at `/settings`, health check at `GET /health`, JSON API at `/api/`.

## Running Tests

```bash
pipenv run pytest
```

Tests use an in-memory SQLite database, so no PostgreSQL setup is needed. Configuration is in `pytest.ini`.

Key test options (already configured in `pytest.ini`):
- `--maxfail=3` stops after 3 failures
- `--cov=app` measures coverage of the `app/` package
- `asyncio_mode = auto` enables async tests without explicit markers

Test fixtures (conftest.py factories, HubSpot response builders) are documented in [testing-guide.md](testing-guide.md).

## Database Migrations

Migrations are managed by Alembic. The async engine configuration in `alembic/env.py` auto-converts PostgreSQL URLs to use the `asyncpg` driver.

```bash
# Apply all pending migrations
pipenv run alembic upgrade head

# Generate a new migration from model changes
pipenv run alembic revision --autogenerate -m "description of change"

# Roll back one migration
pipenv run alembic downgrade -1

# Show current migration state
pipenv run alembic current
```

Migration files live in `alembic/versions/`. Alembic discovers models through the imports in `app/models/__init__.py`.

## CI/CD

GitHub Actions runs on every push and pull request to `main`. The workflow (`.github/workflows/main.yml`):

1. Starts a PostgreSQL 16 service container
2. Sets up Python and installs dependencies via pipenv
3. Runs `alembic upgrade head` against the test database
4. Runs `pytest`

The CI database URL is set to the PostgreSQL service container. Tests themselves use in-memory SQLite regardless of this variable (overridden in `pytest.ini`).

## Deployment

The app deploys to Heroku as a single web dyno.

- **Procfile**: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **DATABASE_URL**: Provided by Heroku's PostgreSQL addon
- **Migrations**: Run `heroku run alembic upgrade head` after deploying schema changes

No Docker. No background workers beyond FastAPI's built-in `BackgroundTasks`. Operations (fetch, score, rescore, export) run as background tasks triggered via the UI or cron hitting the `/api/operations/` endpoints.

## Project Structure

```
email-reviewer/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py             # pydantic-settings configuration
│   ├── database.py           # Async engine, session factory, get_db dependency
│   ├── enums.py              # Enum definitions (EmailDirection, JobType, JobStatus)
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── base.py           # DeclarativeBase, AuditMixin, event listeners
│   │   ├── email.py          # Email model
│   │   ├── rep.py            # Rep model
│   │   ├── score.py          # Score model
│   │   ├── settings.py       # Settings model (single-row config)
│   │   └── job.py            # Job model (operation history)
│   ├── routers/              # HTTP endpoint handlers
│   │   ├── api.py            # JSON API (/api/reps, /api/emails, /api/stats)
│   │   ├── dashboard.py      # HTML views (/, /reps/{rep_email})
│   │   ├── settings.py       # Settings API + HTML (/api/settings, /settings)
│   │   └── operations.py     # Operations API (/api/operations/*)
│   ├── schemas/              # Pydantic request/response schemas
│   │   ├── base.py           # AppBase with from_attributes config
│   │   ├── email.py          # EmailCreate, EmailUpdate, EmailResponse
│   │   ├── rep.py            # RepCreate, RepUpdate, RepResponse, RepLeaderboardRow
│   │   ├── score.py          # ScoringResult, ScoreCreate, ScoreUpdate, ScoreResponse
│   │   ├── stats.py          # StatsResponse
│   │   ├── settings.py       # SettingsResponse, SettingsUpdate
│   │   └── job.py            # JobResponse, JobSummaryResponse, LastRunResponse
│   ├── services/             # Business logic
│   │   ├── export.py         # Excel export of scores and rep averages
│   │   ├── fetcher.py        # HubSpot email fetch and upsert
│   │   ├── rep.py            # Dashboard queries (leaderboard, rep emails, stats)
│   │   ├── scorer.py         # Claude API email scoring
│   │   ├── settings.py       # Settings CRUD (get_settings, update_settings)
│   │   └── job_runner.py     # Job execution (fetch, score, rescore, export)
│   ├── static/               # Static assets
│   │   └── css/style.css     # Score colour utility classes
│   ├── templates/            # Jinja2 HTML templates
│   │   ├── base.html         # Layout with Tailwind CDN and nav
│   │   ├── leaderboard.html  # Rep leaderboard table
│   │   ├── rep_detail.html   # Rep email list with expandable preview
│   │   └── settings.html     # Settings form + operations panel
│   └── templating.py         # Shared Jinja2Templates with cache-bust helper
├── alembic/                  # Migration configuration and scripts
│   ├── env.py                # Async Alembic environment
│   └── versions/             # Migration files
├── docs/                     # Project documentation
│   ├── architecture.md       # System architecture and design decisions
│   ├── coding_standards.md   # Patterns and conventions for coding agents
│   ├── testing-guide.md      # What to test and what not to test
│   └── visual-testing.md     # Selenium screenshot testing
├── scripts/                  # Utility and seed scripts
│   ├── db_reset.py           # Drop all tables and re-apply migrations
│   ├── seed_all.py           # Populate database with seed data
│   └── seeds/                # Seed data definitions
│       ├── reps.py           # Rep seed data
│       ├── emails.py         # Email seed data
│       └── scores.py         # Score seed data
├── tests/                    # Test suite
│   ├── conftest.py           # Fixtures (db, client, factories)
│   ├── fixtures/             # Test data builders
│   │   └── hubspot.py        # HubSpot API response fixtures
│   ├── test_main.py          # Health endpoint
│   ├── test_enums.py         # Enum values
│   ├── test_models.py        # Model registration and relationships
│   ├── test_email_schema.py  # Schema validation
│   ├── test_api_router.py    # JSON API endpoints
│   ├── test_dashboard_router.py # HTML dashboard views
│   ├── test_export.py        # Export service (Excel output)
│   ├── test_fetcher.py       # Fetcher service (HubSpot API mocked)
│   ├── test_scorer.py        # Scorer service (Claude API mocked)
│   ├── test_settings_router.py # Settings API endpoints
│   ├── test_operations_router.py # Operations API endpoints
│   └── test_job_runner.py    # Job runner service
├── .env.example              # Environment variable template
├── .github/workflows/main.yml # CI pipeline
├── alembic.ini               # Alembic configuration
├── CLAUDE.md                 # Coding agent instructions
├── fetch_emails.py           # Standalone HubSpot fetch script (reference)
├── Pipfile                   # Python dependencies
├── Procfile                  # Heroku deployment
└── pytest.ini                # Test configuration
```

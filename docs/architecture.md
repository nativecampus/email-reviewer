# Architecture

## Overview

Email Reviewer fetches outgoing sales rep emails from HubSpot, scores each one using the Claude API, stores results in PostgreSQL, and surfaces them through a web dashboard. The system is built on FastAPI with async SQLAlchemy and deployed to Heroku.

## Data Pipeline

```
HubSpot API -> Fetcher -> PostgreSQL -> Scorer (Claude API) -> PostgreSQL -> Web UI
```

The pipeline runs in discrete stages via CLI commands. Each stage is idempotent: the fetcher upserts on HubSpot ID and the scorer skips emails that already have a score row.

## Layered Architecture

```
enums -> models -> schemas -> services -> routers
```

Dependencies flow strictly left to right.

| Layer | Location | Role |
|-------|----------|------|
| Enums | `app/enums.py` | `(str, Enum)` definitions shared by models and schemas. Serialise as plain strings in the database and JSON. |
| Models | `app/models/` | SQLAlchemy ORM layer. One file per domain entity. All inherit `AuditMixin` and `Base`. |
| Schemas | `app/schemas/` | Pydantic validation. Three schemas per entity: `Create`, `Update`, `Response`. One file per domain. |
| Services | `app/services/` | Business logic. Pure functions where possible. Separated from routers. |
| Routers | `app/routers/` | HTTP endpoints. HTML views (excluded from OpenAPI schema) and JSON API. |

## Database

PostgreSQL in production, async SQLite in tests. The async SQLAlchemy engine uses `asyncpg` as the driver. Session management is handled by a FastAPI dependency (`get_db`) that yields an `AsyncSession`.

### Schema

Three tables:

**emails** - Stores email data fetched from HubSpot.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer (PK) | Auto-increment |
| hubspot_id | String | HubSpot email ID, used for upsert deduplication |
| timestamp | DateTime | When the email was sent |
| from_name | String | Sender display name |
| from_email | String | Sender address (NOT NULL) |
| to_name | String | Recipient display name |
| to_email | String | Recipient address |
| subject | String | Email subject line |
| body_text | Text | Plain-text body |
| direction | String | EMAIL, INCOMING_EMAIL, or FORWARDED_EMAIL |
| fetched_at | DateTime | When the record was fetched from HubSpot |

**scores** - Claude API scoring results. One-to-one with emails (cascade delete).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer (PK) | Auto-increment |
| email_id | Integer (FK -> emails.id) | Unique constraint enforces one score per email |
| personalisation | Integer | 1-10 |
| clarity | Integer | 1-10 |
| value_proposition | Integer | 1-10 |
| cta | Integer | 1-10 |
| overall | Integer | 1-10 |
| notes | Text | Claude's brief explanation |
| score_error | Boolean | True if scoring failed |
| scored_at | DateTime | When the score was generated |

**reps** - Canonical rep identities for name normalisation and leaderboard aggregation.

| Column | Type | Notes |
|--------|------|-------|
| email | String (PK) | Canonical email address |
| display_name | String | Normalised display name |

All three tables include audit columns (`created_at`, `updated_at`, `created_by`, `updated_by`) via `AuditMixin`.

### Relationships

- Email -> Score: one-to-one, cascade delete. Deleting an email removes its score.
- Rep averages are computed as queries, not materialised - the dataset is small enough.

## Audit Trail

Every model inherits `AuditMixin` from `app/models/base.py`. ORM event listeners (`before_insert`, `before_update`) automatically set the audit columns. The current user is resolved from the `CURRENT_USER` environment variable when `AUTH_ENABLED` is false (local dev and test), or from the authenticated request context when enabled.

Routers never set audit fields directly.

## Configuration

`app/config.py` uses `pydantic-settings` to load from environment variables and `.env` file. A singleton `settings` object is instantiated at module level.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite+aiosqlite:///email_reviewer.db` | Database connection string |
| `HUBSPOT_ACCESS_TOKEN` | (empty) | HubSpot API authentication |
| `ANTHROPIC_API_KEY` | (empty) | Claude API authentication |
| `AUTH_ENABLED` | `False` | Toggle authentication |
| `CURRENT_USER` | `system` | Audit trail identity when auth is disabled |

## Migrations

Managed by Alembic with async support. The `alembic/env.py` file converts PostgreSQL URLs to use the `asyncpg` driver automatically. Migrations are applied with `alembic upgrade head` and live in `alembic/versions/`.

## Scorer

`app/services/scorer.py` scores unscored emails via the Claude API (claude-sonnet-4-20250514). The entry point is `score_unscored_emails(session, batch_size=5)`, which:

1. Queries emails with no matching score record (LEFT JOIN scores WHERE NULL).
2. Auto-scores emails with empty or very short bodies (under 20 words) as all 1s without calling Claude. The score notes explain why.
3. Sends remaining emails to Claude concurrently, capped by an asyncio semaphore (`batch_size`).
4. Retries once on JSON parse failure. After two consecutive failures, writes a score row with `score_error=True`.
5. Returns a summary dict with counts (`total_unscored`, `scored`, `auto_scored`, `errors`) and token usage.

`_build_user_message(email)` formats the email's From, To, Subject, Date, and Body fields into a prompt string. Body text is truncated to 4000 characters.

`SCORING_SYSTEM_PROMPT` instructs Claude to return a JSON object with five 1-10 scores (personalisation, clarity, value_proposition, cta, overall) and a notes field. Responses are validated through the `ScoringResult` Pydantic model.

## Key Design Decisions

**Async throughout** - The entire stack is async (FastAPI, SQLAlchemy async sessions, asyncpg). This aligns with the concurrent Claude API calls in the scorer and avoids mixing sync and async database access.

**PostgreSQL with SQLite test fallback** - Production uses PostgreSQL for reliability and Heroku compatibility. Tests use in-memory SQLite for speed and isolation. A compiler extension maps PostgreSQL-specific types (JSONB) to SQLite equivalents.

**Idempotent operations** - Both the fetcher (upsert on hubspot_id) and scorer (skip emails with existing scores) are safe to re-run. Partial failures leave the database in a consistent state.

**Pydantic validation at the boundary** - Score range validation (1-10) lives in Pydantic schemas, not database constraints. This gives clear error messages at the API layer rather than database-level constraint violations.

**Heroku deployment** - No Docker. The app runs as a single web dyno via Procfile (`uvicorn`). DATABASE_URL comes from Heroku's PostgreSQL addon. This keeps the deployment simple for an internal tool.

**CLI-first workflow** - Fetching and scoring run as CLI commands, not background jobs. The web UI is read-only. This avoids the complexity of task queues for a system that runs on demand.

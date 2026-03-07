# Architecture

## Overview

Email Reviewer fetches outgoing sales rep emails from HubSpot, scores each one using the Claude API, stores results in PostgreSQL, and surfaces them through a web dashboard. The system is built on FastAPI with async SQLAlchemy and deployed to Heroku.

## Data Pipeline

```
HubSpot API -> Fetcher -> PostgreSQL -> Scorer (Claude API) -> PostgreSQL -> Web UI
```

The pipeline runs in discrete stages as background tasks triggered via the web UI or API. Each stage is idempotent: the fetcher upserts on HubSpot ID and the scorer skips emails that already have a score row.

## Layered Architecture

```
enums -> models -> schemas -> services -> routers
```

Dependencies flow strictly left to right.

| Layer | Location | Role |
|-------|----------|------|
| Enums | `app/enums.py` | `(str, Enum)` definitions shared by models and schemas. Serialise as plain strings in the database and JSON. Includes `EmailDirection`, `JobType` (FETCH, SCORE, RESCORE, EXPORT, Chain_Build), `JobStatus`. |
| Models | `app/models/` | SQLAlchemy ORM layer. One file per domain entity. All inherit `AuditMixin` and `Base`. |
| Schemas | `app/schemas/` | Pydantic validation. Three schemas per entity: `Create`, `Update`, `Response`. One file per domain. |
| Services | `app/services/` | Business logic. Pure functions where possible. Separated from routers. |
| Routers | `app/routers/` | HTTP endpoints. HTML views (excluded from OpenAPI schema) and JSON API. |

## Database

PostgreSQL in production, async SQLite in tests. The async SQLAlchemy engine uses `asyncpg` as the driver. Session management is handled by a FastAPI dependency (`get_db`) that yields an `AsyncSession`.

### Schema

Seven tables:

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
| chain_id | Integer (FK -> email_chains.id) | Nullable. Links email to a conversation chain |
| position_in_chain | Integer | Nullable. Ordinal position within the chain |
| open_count | Integer | Nullable. HubSpot engagement open count |
| click_count | Integer | Nullable. HubSpot engagement click count |
| reply_count | Integer | Nullable. HubSpot engagement reply count |
| message_id | String | Nullable. RFC 2822 Message-ID header |
| in_reply_to | String | Nullable. RFC 2822 In-Reply-To header |
| thread_id | String | Nullable. HubSpot thread identifier |

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

**reps** - Canonical rep identities for name normalisation and team aggregation.

| Column | Type | Notes |
|--------|------|-------|
| email | String (PK) | Canonical email address |
| display_name | String | Normalised display name |

**settings** - Single-row application configuration. Seeded on first migration.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer (PK) | Always 1 (enforced by check constraint) |
| global_start_date | Date | Floor for all fetches. Default 2025-09-01 |
| company_domains | String | Comma-separated domains for outgoing email filtering |
| scoring_batch_size | Integer | Concurrency limit for Claude API calls. Default 5 |
| auto_score_after_fetch | Boolean | When true, fetch also scores unscored emails. Default true |
| initial_email_prompt | Text | Configurable prompt for individual email scoring. Defaults to four-dimension scoring prompt (personalisation, clarity, value_proposition, cta) |
| chain_email_prompt | Text | Prompt for scoring emails within a conversation chain context |
| chain_evaluation_prompt | Text | Prompt for evaluating conversation chains (progression, responsiveness, persistence, conversation_quality) |
| weight_value_proposition | Float | Weight for value_proposition in overall score calculation. Default 0.35 |
| weight_personalisation | Float | Weight for personalisation in overall score calculation. Default 0.30 |
| weight_cta | Float | Weight for cta in overall score calculation. Default 0.20 |
| weight_clarity | Float | Weight for clarity in overall score calculation. Default 0.15 |

**jobs** - Operation execution history.

| Column | Type | Notes |
|--------|------|-------|
| job_id | Integer (PK) | Auto-increment |
| job_type | String | FETCH, SCORE, RESCORE, EXPORT, or Chain_Build |
| status | String | PENDING, RUNNING, COMPLETED, or FAILED |
| started_at | DateTime | Set when status becomes RUNNING |
| completed_at | DateTime | Set when status becomes COMPLETED or FAILED |
| result_summary | JSON | Operation-specific results (e.g. fetched count, scored count) |
| error_message | Text | Error details on FAILED status |
| triggered_by | String | "cron" or "ui" |

**email_chains** - Groups related emails into conversation threads.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer (PK) | Auto-increment |
| normalized_subject | String | Subject line with Re:/Fwd: prefixes stripped |
| participants | String | Sorted comma-separated email addresses in the chain |
| started_at | DateTime | Timestamp of the first email in the chain |
| last_activity_at | DateTime | Timestamp of the most recent email in the chain |
| email_count | Integer | Total emails in the chain |
| outgoing_count | Integer | Outgoing emails in the chain |
| incoming_count | Integer | Incoming emails in the chain |

**chain_scores** - Conversation-level scoring results. One-to-one with email_chains (cascade delete).

| Column | Type | Notes |
|--------|------|-------|
| id | Integer (PK) | Auto-increment |
| chain_id | Integer (FK -> email_chains.id) | Unique constraint enforces one score per chain |
| progression | Integer | 1-10. How well the conversation advances toward the sales goal |
| responsiveness | Integer | 1-10. Timeliness and relevance of follow-ups |
| persistence | Integer | 1-10. Appropriate follow-up cadence |
| conversation_quality | Integer | 1-10. Overall multi-touch engagement quality |
| avg_response_hours | Float | Nullable. Average response time in hours |
| notes | Text | Nullable. Claude's explanation of the chain scores |
| score_error | Boolean | True if scoring failed |
| scored_at | DateTime | When the score was generated |

All seven tables include audit columns (`created_at`, `updated_at`, `created_by`, `updated_by`) via `AuditMixin`.

### Relationships

- Email -> Score: one-to-one, cascade delete. Deleting an email removes its score.
- EmailChain -> Email: one-to-many. Emails reference their chain via chain_id.
- EmailChain -> ChainScore: one-to-one, cascade delete. Deleting a chain removes its chain_score.
- Rep averages are computed as queries, not materialised - the dataset is small enough.

## Audit Trail

Every model inherits `AuditMixin` from `app/models/base.py`. ORM event listeners (`before_insert`, `before_update`) automatically set the audit columns. The current user is resolved from the `CURRENT_USER` environment variable when `AUTH_ENABLED` is false (local dev and test), or from the authenticated request context when enabled.

Routers never set audit fields directly.

## Configuration

`app/config.py` uses `pydantic-settings` to load from environment variables and `.env` file. A singleton `settings` object is instantiated at module level.

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_NAME` | `Email Reviewer` | Application name |
| `APP_VERSION` | `0.1.0` | Application version |
| `DATABASE_URL` | `sqlite+aiosqlite:///email_reviewer.db` | Database connection string |
| `HUBSPOT_ACCESS_TOKEN` | (empty) | HubSpot API authentication |
| `ANTHROPIC_API_KEY` | (empty) | Claude API authentication |
| `AUTH_ENABLED` | `False` | Toggle authentication |
| `CURRENT_USER` | `system` | Audit trail identity when auth is disabled |
| `REDIS_URL` | (empty) | Redis connection string for RQ worker queue. When empty, jobs run as FastAPI BackgroundTasks. |

## Migrations

Managed by Alembic with async support. The `alembic/env.py` file converts PostgreSQL URLs to use the `asyncpg` driver automatically. Migrations are applied with `alembic upgrade head` and live in `alembic/versions/`.

## Fetcher

`app/services/fetcher.py` ingests outgoing and incoming emails from the HubSpot CRM v3 search API. The entry point is `fetch_and_store(session, access_token, company_domains, ...)`, which:

1. Calls `fetch_emails_from_hubspot()` to paginate through HubSpot search results with retry logic (exponential backoff on errors, respects `Retry-After` on 429s). When `max_count` is set, passes `max_results=int(max_count * 1.5)` to stop pagination early — the 1.5x multiplier accounts for irrelevant emails that will be filtered out. HubSpot's search API has a 10,000 result paging limit; when hit, the fetcher automatically subdivides the date range into halves and fetches each recursively, deduplicating by HubSpot ID at the boundary.
2. Calls `filter_relevant_emails()` to keep emails involving company reps. EMAIL direction is kept when the from_email domain is in company_domains (outgoing from our rep). INCOMING_EMAIL direction is kept when the to_email domain is in company_domains (reply to our rep). FORWARDED_EMAIL and all other directions are dropped.
3. Applies `max_count` (if provided) to the filtered list, limiting stored emails.
4. Calls `upsert_emails_to_db()` to upsert on `hubspot_id` and auto-create Rep records for new sender addresses (outgoing emails only). Parses `hs_timestamp` from HubSpot into the `timestamp` column. Stores engagement metrics (open_count, click_count, reply_count) and threading headers (message_id, in_reply_to, thread_id).

Returns the number of emails stored.

## Scorer

`app/services/scorer.py` scores unscored emails and conversation chains via the Claude API (claude-sonnet-4-20250514).

### Individual Email Scoring

The entry point is `score_unscored_emails(session, batch_size=5)`, which:

1. Queries emails with no matching score record (LEFT JOIN scores WHERE NULL).
2. Skips emails with empty or very short bodies (under 20 words) — no score row is created since there is no content to evaluate.
3. Loads the scoring prompt from settings: `initial_email_prompt` for standalone emails or first-in-chain, `chain_email_prompt` for follow-up emails (position_in_chain > 1).
4. For follow-up emails, pre-builds chain context via `_build_chain_context()` — prior emails in the chain, each truncated to 2000 characters, included as a "Previous conversation" section in the user message.
5. Sends remaining emails to Claude concurrently, capped by an asyncio semaphore (`batch_size`).
6. Retries on rate limit (429) errors using the `retry-after` header from the API response, up to 5 attempts. Falls back to 60 seconds when the header is missing.
7. Retries once on JSON parse failure. After two consecutive failures, writes a score row with `score_error=True`.
8. Parses 4 dimensions from Claude (personalisation, clarity, value_proposition, cta) via the `ScoringResult` Pydantic model. Calculates `overall` as a weighted average using weights from settings via `_calculate_weighted_overall()`. Stores all 5 values in the scores table.
9. Calls `score_unscored_chains()` after individual scoring.
10. Returns a summary dict with counts (`total_unscored`, `scored`, `skipped`, `errors`, `chains_scored`, `chain_errors`) and token usage.

`_calculate_weighted_overall(scores, weights)` is a pure function that computes the weighted sum of the 4 dimensions, rounds to the nearest integer, and clamps the result to 1-10.

`_build_user_message(email)` formats the email's From, To, Subject, Date, and Body fields into a prompt string. Body text is truncated to 4000 characters. For follow-up emails, a "Previous conversation" section with chain context is prepended.

`_build_chain_context(session, email)` fetches all prior emails in the same chain (by position), formats each with From/To/Date/Subject/Body (body truncated to 2000 chars), and joins them with separators. Returns empty string for emails without a chain or at position 1.

`DEFAULT_INITIAL_PROMPT` is a module-level constant preserved as the default value for `settings.initial_email_prompt`. Actual scoring always reads the prompt from settings.

### Chain-Level Scoring

`score_unscored_chains(session, batch_size=5)` scores conversation chains that have no chain_score record and have email_count >= 2:

1. Builds full conversation context from all chain emails.
2. Sends to Claude with `settings.chain_evaluation_prompt`.
3. Parses 4 chain dimensions (progression, responsiveness, persistence, conversation_quality) via `ChainScoringResult`.
4. Computes `avg_response_hours` from timestamps of consecutive outgoing emails.
5. Retries once on parse failure. After two failures, writes a chain_score with `score_error=True`.
6. Returns a summary dict with `chains_scored`, `errors`, and token usage.

## Chain Builder

`app/services/chain_builder.py` groups emails into conversation chains. The entry point is `build_chains(session)`, which:

1. Loads all emails ordered by timestamp.
2. Runs three matching passes in priority order:
   - **Message-ID threading**: Links emails where one's `in_reply_to` matches another's `message_id`.
   - **Thread-ID grouping**: Groups unchained emails that share the same HubSpot `thread_id`. Does not merge chains already formed by message-ID matching.
   - **Subject + participant fallback**: Groups remaining unchained emails by normalized subject, at least one overlapping participant (`from_email` or `to_email`), and timestamps within 30 days.
3. For each group of 2+ emails: creates an `EmailChain` row with `normalized_subject`, sorted comma-separated `participants`, `started_at`, `last_activity_at`, `email_count`, `outgoing_count`, `incoming_count`. Sets `chain_id` and `position_in_chain` (1-based, by timestamp) on each email.
4. Returns a dict with `chains_created`, `chains_updated`, and `emails_linked` counts.

The service is idempotent - running it twice produces the same result. Existing chain assignments are cleared and rebuilt on each run.

`normalize_subject(subject)` is a pure function that recursively strips `Re:`, `RE:`, `Fwd:`, `FW:`, `Fw:` prefixes and trims whitespace. Returns empty string for `None` input.

## Exporter

`app/services/export.py` generates an Excel workbook from scored email data. The entry point is `export_to_excel(session, output_path)`, which:

1. Queries all emails with a non-error score record.
2. Writes an "Email Scores" sheet with one row per scored email: rep name, subject, date, five score dimensions, and notes. Score cells are colour-coded by value (green >= 8, yellow >= 6, orange >= 4, red < 4).
3. Writes a "Rep Averages" sheet with one row per rep: average of each score dimension, sorted by overall average descending.

Both sheets use Arial font, frozen header rows, and auto-filters. Returns the output file path.

A second entry point, `export_rep_emails(session, rep_email, *, search, date_from, date_to, score_min, score_max, export_all)`, generates an in-memory Excel workbook (BytesIO) for a single rep's emails. Accepts the same filter parameters as `get_rep_emails()`. When `export_all=True`, all filter params are ignored and every scored email for the rep is included. The workbook contains a single "Email Scores" sheet with the same colour-coded formatting as the full export.

## Dashboard and API

The web UI is served by four routers registered in `app/main.py`.

### HTML Dashboard (`app/routers/dashboard.py`)

HTML views excluded from the OpenAPI schema (`include_in_schema=False`). Rendered via Jinja2 templates with a pre-built Tailwind CSS file.

| Route | View |
|-------|------|
| `GET /` | Team page — rep table with colour-coded average scores, links to rep detail. Accepts `?page=1&per_page=20` query params for pagination. `per_page=0` returns all results. |
| `GET /reps/{rep_email}` | Rep detail page — scored email list with expandable body preview, plus a Chains section showing the rep's conversation chains. Accepts `?page=1&per_page=20` query params for pagination. `per_page=0` returns all results. Also accepts `?search=`, `?date_from=YYYY-MM-DD`, `?date_to=YYYY-MM-DD`, `?score_min=1..10`, `?score_max=1..10` for filtering. Filters apply via ILIKE on subject/body, inclusive date range on timestamp, and inclusive range on overall score. |
| `GET /reps/{rep_email}/export` | Downloads an Excel (.xlsx) file of the rep's scored emails. Accepts the same filter query params as the detail page plus `?export_all=true` to ignore filters and include all emails. |
| `GET /chains/{chain_id}` | Chain detail page — full conversation thread in chronological order. Each email shows direction, sender, recipient, timestamp, subject, body preview, and individual score. Chain score panel at top with all 4 dimensions and avg_response_hours. Accessed from the rep detail page's Chains section. |

### Settings Page (`app/routers/settings.py`)

| Route | View |
|-------|------|
| `GET /settings` | Tabbed settings page (HTML, excluded from OpenAPI). Accepts `?tab=` query parameter: `general` (default), `scoring`, `chain-evaluation`. All tab content is rendered server-side; JS toggles visibility. |

### JSON API (`app/routers/api.py`)

| Route | Response |
|-------|----------|
| `GET /api/reps` | List of `RepTeamRow` objects sorted by overall avg descending. Each object includes `chain_count` and `avg_chain_score` fields. |
| `GET /api/reps/{rep_email}/emails` | Scored emails for one rep, ordered by date descending |
| `GET /api/reps/{rep_email}/chains` | Paginated chains where the rep is a sender. Returns `{items, total, page, per_page}`. |
| `GET /api/chains/{chain_id}` | Single chain with all emails in timestamp order and chain_score. Returns 404 if not found. |
| `GET /api/emails/{email_id}` | Single email with its score detail |
| `GET /api/stats` | `StatsResponse` with total_emails, total_scored, total_reps, avg_overall |

### Settings API (`app/routers/settings.py`)

| Route | Response |
|-------|----------|
| `GET /api/settings` | Current `SettingsResponse` |
| `PATCH /api/settings` | Partial update, returns updated `SettingsResponse` |
| `GET /api/settings/defaults` | Default prompt texts for `initial_email_prompt`, `chain_email_prompt`, `chain_evaluation_prompt`. Powers "Reset to Default" buttons. |

### Operations API (`app/routers/operations.py`)

| Route | Response |
|-------|----------|
| `POST /api/operations/fetch` | 202 with job record. Rejects 409 if a FETCH job is RUNNING. Accepts optional JSON body with `start_date`, `end_date` (date strings), `max_count` (int), and `auto_score` (bool) to override default fetch behaviour. When `auto_score` is provided it overrides the `auto_score_after_fetch` setting for this fetch only; when omitted the setting applies. Params are stored in `result_summary.params`. |
| `POST /api/operations/score` | 202 with job record. Rejects 409 if SCORE or RESCORE is RUNNING. |
| `POST /api/operations/rescore` | 202 with job record. Rejects 409 if SCORE or RESCORE is RUNNING. |
| `POST /api/operations/export` | 202 with job record. |
| `POST /api/operations/chain-build` | 202 with job record. Rejects 409 if a CHAIN_BUILD job is RUNNING. |
| `GET /api/operations/jobs` | List of `JobResponse` ordered by created_at desc |
| `GET /api/operations/jobs/{job_id}` | Single `JobResponse` |
| `GET /api/operations/last-run` | Most recent completed job per type (or null) |

### Rep Service (`app/services/rep.py`)

Async query functions used by both routers:

- `get_team(session, *, page=1, per_page=20)` — JOINs emails/scores/reps, GROUPs BY rep, computes AVGs (including `chain_count` and `avg_chain_score`), sorts by overall descending. Returns paginated dict `{items, total, page, per_page, pages}`. Pass `per_page=None` or `0` to return all results.
- `get_rep_emails(session, rep_email, *, page=1, per_page=20, search=None, date_from=None, date_to=None, score_min=None, score_max=None)` — scored emails for one rep, ordered by date descending. Returns paginated dict `{items, total, page, per_page, pages}`. Pass `per_page=None` or `0` to return all results. Optional filters: `search` (ILIKE on subject/body_text), `date_from`/`date_to` (inclusive range on timestamp), `score_min`/`score_max` (inclusive range on overall score). Filters apply before pagination; total reflects the filtered count.
- `get_email_detail(session, email_id)` — single email with its score (eager loaded)
- `get_stats(session)` — summary counts (total_emails, total_scored, total_reps) and avg_overall

### Chain Service (`app/services/chain.py`)

Async query functions for chain visibility:

- `get_chain_detail(session, chain_id)` — single chain with all emails in timestamp order and chain_score. Returns None if not found.
- `get_rep_chains(session, rep_email, page=1, per_page=20)` — chains where any email has from_email matching rep_email. Same pagination shape.

### Templating (`app/templating.py`)

Shared `Jinja2Templates` instance with a `static_url()` global that appends an MD5 hash query parameter for cache-busting.

### Static Assets

`app/static/css/tailwind.css` is a pre-built Tailwind CSS file generated by the Tailwind CLI from `app/static/css/input.css`. Rebuild after changing Tailwind classes in templates: `npx @tailwindcss/cli -i app/static/css/input.css -o app/static/css/tailwind.css --minify`.

`app/static/css/style.css` provides score colour utility classes (`score-high`, `score-mid`, `score-low`) keyed to score thresholds (>=7 green, >=4 yellow, <4 red). Static files are mounted at `/static`.

## Settings

`app/services/settings.py` manages application configuration stored in a single-row `settings` table. The entry point is `get_settings(session)`, which returns the settings row and creates it with defaults if missing. `update_settings(session, updates)` applies partial updates.

Settings control the behaviour of fetch and score operations:

- `global_start_date` — floor for all HubSpot fetches. The effective start date for a fetch is `max(global_start_date, max_fetched_at_in_db or global_start_date)`.
- `company_domains` — comma-separated list passed to `filter_relevant_emails`.
- `scoring_batch_size` — concurrency limit for the Claude API semaphore.
- `auto_score_after_fetch` — when true, a fetch operation automatically scores unscored emails on completion.
- `initial_email_prompt` — configurable system prompt for individual email scoring. Defaults to four-dimension scoring (personalisation, clarity, value_proposition, cta).
- `chain_email_prompt` — system prompt for scoring emails within conversation chain context.
- `chain_evaluation_prompt` — system prompt for evaluating conversation chains on chain-specific dimensions (progression, responsiveness, persistence, conversation_quality).
- `weight_value_proposition`, `weight_personalisation`, `weight_cta`, `weight_clarity` — weights for computing an overall score from the four individual dimensions. Must sum to 1.0. Defaults: 0.35, 0.30, 0.20, 0.15.

Validation lives in the `SettingsUpdate` Pydantic schema: `global_start_date` cannot be in the future, `company_domains` cannot be empty, `scoring_batch_size` must be >= 1. When any weight field is provided, all four must be present and sum to 1.0 (tolerance 0.001). Prompt fields cannot be empty strings.

## Job Runner

`app/services/job_runner.py` executes operations as background tasks or RQ worker jobs. Each runner accepts an optional `session` parameter — when `None` (worker process), a new `AsyncSession` is created from `AsyncSessionLocal`. Each runner follows the same pattern: set RUNNING with `started_at`, execute, set COMPLETED/FAILED with `completed_at` and `result_summary`/`error_message`. All wrapped in try/except.

`app/tasks.py` provides synchronous wrapper functions (`fetch_task`, `score_task`, `rescore_task`, `export_task`) for RQ. Each calls `asyncio.run()` on the corresponding async runner with `session=None`, so the runner creates its own session.

- `run_fetch_job(session, job_id, *, fetch_start_date, fetch_end_date, max_count, auto_score)` — reads settings, computes effective start date (overridden when `fetch_start_date` is provided), calls `fetch_and_store` with company_domains and optional `end_date`/`max_count`. Runs `build_chains` after fetch to group emails into conversation chains. Runs scoring after chain building when `auto_score` is true, or when `auto_score` is None and the `auto_score_after_fetch` setting is true. Result summary includes `fetched`, `new_reps`, and optionally `scored`, `errors`, `tokens`.
- `run_score_job(session, job_id)` — reads `scoring_batch_size` from settings, calls `score_unscored_emails`. Result summary includes `scored`, `errors`, `tokens`.
- `run_rescore_job(session, job_id)` — deletes all existing chain_scores and scores, then calls `score_unscored_emails` to score every email and chain. Result summary includes `scored`, `errors`, `tokens`, `chains_scored`, `chain_errors`.
- `run_export_job(session, job_id, output_path)` — generates Excel via `export_to_excel`, stores path in result summary.
- `run_chain_build_job(session, job_id)` — calls `build_chains`, stores result summary with `chains_created`, `chains_updated`, and `emails_linked` counts.

No FULL_RUN job type. A FETCH job can handle both fetch and score phases. The `auto_score` request parameter controls scoring per-fetch; when omitted, the `auto_score_after_fetch` setting applies. Cron POSTs to `/api/operations/fetch` and the setting controls the default behaviour. The UI exposes a "Score after fetch" checkbox initialised from the setting, allowing per-fetch override.

## Key Design Decisions

**Async throughout** - The entire stack is async (FastAPI, SQLAlchemy async sessions, asyncpg). This aligns with the concurrent Claude API calls in the scorer and avoids mixing sync and async database access.

**PostgreSQL with SQLite test fallback** - Production uses PostgreSQL for reliability and Heroku compatibility. Tests use in-memory SQLite for speed and isolation. A compiler extension maps PostgreSQL-specific types (JSONB) to SQLite equivalents.

**Idempotent operations** - Both the fetcher (upsert on hubspot_id) and scorer (skip emails with existing scores) are safe to re-run. Partial failures leave the database in a consistent state.

**Pydantic validation at the boundary** - Score range validation (1-10) lives in Pydantic schemas, not database constraints. This gives clear error messages at the API layer rather than database-level constraint violations.

**Heroku deployment** - No Docker. The app runs on Heroku with a web dyno (`uvicorn`) and an optional worker dyno (`rq worker`). DATABASE_URL comes from Heroku's PostgreSQL addon. REDIS_URL comes from a Redis addon (e.g. Heroku Data for Redis).

**Worker dyno and Redis queue** - When `REDIS_URL` is configured, operations are enqueued to an RQ (Redis Queue) job queue named `email-reviewer`. A separate worker dyno dequeues and runs jobs in their own process, freeing the web dyno from long-running tasks. The worker creates its own async database session via `AsyncSessionLocal`.

**Fallback to BackgroundTasks** - When `REDIS_URL` is empty (local dev, or production without Redis), the operations router falls back to FastAPI `BackgroundTasks`. The same async job runner functions are called in-process. This means the app works without Redis - adding Redis is purely additive.

**Redis health validation** - When `REDIS_URL` is configured, the operations router validates Redis connectivity and worker availability before creating a job record. If Redis is unreachable or no workers are listening on the `email-reviewer` queue, the API returns 503 with a diagnostic message. Validation runs before the job is committed to the database, preventing orphaned PENDING records.

**Operations lifecycle** - Each operation creates a job record (PENDING), then either enqueues to RQ or adds a BackgroundTask. The job transitions through RUNNING to COMPLETED or FAILED. Conflict prevention rejects new operations when a conflicting job is already RUNNING (e.g. only one FETCH at a time). Cron hits the same API endpoints as the UI.

**Stale job reaping** - When listing jobs or starting a new operation, the operations router marks stale jobs as FAILED. PENDING jobs older than 10 minutes and RUNNING jobs older than 60 minutes are reaped. This handles cases where a worker crashes (e.g. RQ fork failure) and never transitions the job out of PENDING/RUNNING.

**Single-row settings** - Application configuration lives in a `settings` table with a check constraint enforcing `id = 1`. Seeded on the initial migration. Avoids config files and environment variable sprawl for runtime-adjustable values.

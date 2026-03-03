# email-reviewer

# Dev Brief: Automated Email Scoring System

## Overview

Build a system that fetches outgoing sales rep emails from HubSpot, scores each one using the Claude API, stores everything in PostgreSQL, and surfaces results through a simple web dashboard.

The existing HubSpot fetch script (`fetch_emails.py`, attached) handles email retrieval and should be used as the foundation. The scoring layer calls the Claude API to evaluate each outgoing email against a rubric. Results live in Postgres and are displayed via a lightweight web UI.

---

## Architecture

```
HubSpot API → Fetcher → Postgres → Scorer (Claude API) → Postgres → Web UI
```

Four modules:

1. **Fetcher** — adapted from existing `fetch_emails.py`, writes to Postgres
2. **Scorer** — reads unscored emails from Postgres, sends to Claude API, writes scores back
3. **Database** — Postgres schema and queries
4. **Web UI** — lightweight dashboard showing rep leaderboard and individual email scores

---

## Module 1: Fetcher (adapt existing script)

Use the attached `fetch_emails.py` as the base. It already handles HubSpot v3 search, pagination, rate limiting, and date filtering.

### Modifications needed

- Extract the fetch logic into an importable function (not just CLI `main()`)
- After fetching, **filter to outgoing emails only** — keep rows where `direction` is `EMAIL` or `FORWARDED_EMAIL` (these are sent by reps). Exclude `INCOMING_EMAIL`.
- Also filter out emails where `from_email` does not contain `nativecampusadvertising.com` or `native.fm` — this catches edge cases where direction metadata is wrong
- Strip `body_html` before sending to the scorer (we don't need it for scoring, and it burns tokens). Keep `body_text` only.
- The fetcher should upsert into the `emails` table (see Module 3: Database). Use the HubSpot `id` as the natural key to avoid duplicates on re-runs.

### Environment

- `HUBSPOT_ACCESS` env var (already in existing script)
- `ANTHROPIC_API_KEY` env var for the scorer
- `DATABASE_URL` env var for Postgres connection

---

## Module 2: Scorer (Claude API)

### Model

Use `claude-sonnet-4-20250514`. It's fast and cheap enough for bulk scoring. Do not use Opus for this.

### Prompt design

Send each email to Claude with a system prompt containing the scoring rubric. The system prompt should be something along these lines (refine as needed):

```
You are an email quality assessor for a sales team at a campus advertising company. You score outgoing sales/outreach emails on 5 criteria, each rated 1-10.

## Scoring Criteria

### Personalisation (1-10)
- 1-3: No recipient name, no business name, completely generic
- 4-5: Uses a name but nothing else tailored
- 6-7: References the specific business, their sector, or prior conversation
- 8-10: Clearly written for this specific recipient with unique context

### Clarity (1-10)
- 1-3: Confusing, poorly structured, hard to follow
- 4-5: Understandable but messy or verbose
- 6-7: Clear structure, easy to read
- 8-10: Concise, well-organised, professional

### Value Proposition (1-10)
- 1-3: No reason given for the recipient to care
- 4-5: Generic benefits mentioned
- 6-7: Specific benefits relevant to the recipient's business type
- 8-10: Compelling, data-backed, tailored value prop

### Call to Action (1-10)
- 1-3: No clear next step or ask
- 4-5: Vague ask ("let me know")
- 6-7: Clear specific ask (call, meeting, reply)
- 8-10: Easy to act on with low friction (e.g. includes booking link, specific times)

### Overall (1-10)
- Holistic assessment: would this email get a response from a busy business owner?
- Factor in grammar, spelling, tone, and professionalism
- Penalise: obvious template merge failures (blank fields), typos, empty emails
- Reward: genuine human feel, honesty, good follow-up etiquette

## Additional rules
- If the email body is empty or nearly empty (under 20 words), score everything 1
- If there's a merge/template failure (e.g. a blank where a name should be), cap Personalisation at 3 and Overall at 5
- Reply emails and follow-ups should be scored in context — a short "thanks, sorting that now" is fine if it's a reply, don't penalise brevity in conversational threads
- Score the REP'S writing only, ignore quoted/forwarded content from the other party
```

### User message format

Each user message should contain the email metadata and body:

```
Score this email:

From: {from_name} <{from_email}>
To: {to_name} <{to_email}>
Subject: {subject}
Date: {timestamp}

Body:
{body_text}
```

### Response format

Force structured JSON output. Set the response to return exactly this shape:

```json
{
  "personalisation": 7,
  "clarity": 8,
  "value_proposition": 6,
  "cta": 7,
  "overall": 7,
  "notes": "Brief 1-2 sentence explanation of the score"
}
```

Use a system prompt instruction to respond ONLY with the JSON object, no markdown, no preamble. Parse the response and validate that all 5 scores are integers 1-10. If parsing fails, retry once, then flag the email as `"score_error": true` and move on.

### Batching and rate limits

- Use the Anthropic Python SDK (`anthropic` package)
- Process emails concurrently using `asyncio` with a semaphore to cap at **5 concurrent requests** (stay well within Sonnet rate limits)
- Add a `--batch-size` CLI arg defaulting to 50, with a brief pause between batches
- Log progress: `Scored 47/312 emails...`
- If an email's `body_text` exceeds 4000 characters, truncate to 4000 chars before sending (long emails are usually signature/thread noise anyway — the important content is at the top)

### Cost awareness

Roughly estimate: ~500 input tokens + ~100 output tokens per email. At Sonnet pricing that's fractions of a cent each. For 1000 emails you're looking at well under $1. Log total tokens used at the end of a run.

---

## Module 3: Database (PostgreSQL)

### Schema

```sql
CREATE TABLE emails (
    id TEXT PRIMARY KEY,                    -- HubSpot email ID
    created_at TIMESTAMPTZ,
    timestamp TIMESTAMPTZ,
    from_name TEXT,
    from_email TEXT NOT NULL,
    to_name TEXT,
    to_email TEXT,
    subject TEXT,
    body_text TEXT,
    direction TEXT,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scores (
    id SERIAL PRIMARY KEY,
    email_id TEXT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    personalisation INT CHECK (personalisation BETWEEN 1 AND 10),
    clarity INT CHECK (clarity BETWEEN 1 AND 10),
    value_proposition INT CHECK (value_proposition BETWEEN 1 AND 10),
    cta INT CHECK (cta BETWEEN 1 AND 10),
    overall INT CHECK (overall BETWEEN 1 AND 10),
    notes TEXT,
    score_error BOOLEAN DEFAULT FALSE,
    scored_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email_id)                        -- one score per email
);

CREATE TABLE reps (
    email TEXT PRIMARY KEY,                 -- canonical email address
    display_name TEXT NOT NULL              -- normalised name
);

CREATE INDEX idx_emails_from ON emails(from_email);
CREATE INDEX idx_emails_timestamp ON emails(timestamp);
CREATE INDEX idx_scores_overall ON scores(overall);
```

### Notes

- The `reps` table handles name normalisation. When the fetcher encounters a new `from_email`, insert into `reps` if not exists. Display name can be manually corrected later (e.g. "Matthew Billington" → "Matt Billington"). The UI and all aggregation should JOIN on `reps.email` to get the canonical display name.
- Rep averages are computed as views/queries, not materialised — the dataset is small enough that this is fine.
- Use `psycopg2` or `asyncpg` (if you're already async for the scorer, `asyncpg` makes sense).
- The scorer should query for emails that have no matching row in `scores` — this makes re-runs idempotent. Only unscored emails get sent to Claude.

---

## Module 4: Web UI

### Stack

Keep it simple: **FastAPI** backend + a basic frontend. Use either plain HTML/Jinja2 templates or a single React page — dealer's choice, but don't over-engineer it. This is a baby dashboard, not a product.

### Pages / Views

#### 1. Rep Leaderboard (home page)

A table showing all reps ranked by overall average score. Columns:

| Rep Name | Emails Scored | Personalisation | Clarity | Value Prop | CTA | Overall |
|---|---|---|---|---|---|---|

- Colour-code the score cells (green ≥8, yellow ≥6, orange ≥4, red <4) — same scheme as the Excel output
- Clicking a rep name drills into their individual email list
- Show the date range of scored emails at the top

#### 2. Rep Detail Page

Shows all scored emails for a single rep, sorted by date descending. Columns:

| Date | To | Subject | Pers. | Clarity | Value | CTA | Overall | Notes |
|---|---|---|---|---|---|---|---|---|

- Same colour coding on score cells
- Clicking a row expands to show the full email body (accordion or modal — keep it simple)

#### 3. Email Detail (optional, nice-to-have)

Full view of a single email with its scores and Claude's notes. Not critical for v1 — the expandable row on the rep detail page is sufficient.

### API Endpoints

```
GET /api/reps                          → rep leaderboard data
GET /api/reps/{email}/emails           → scored emails for one rep
GET /api/emails/{id}                   → single email + scores
GET /api/stats                         → summary stats (total emails, avg scores, date range)
POST /api/fetch                        → trigger a HubSpot fetch (optional, can stay CLI-only for v1)
POST /api/score                        → trigger scoring of unscored emails (optional, can stay CLI-only for v1)
```

### Design

Don't spend ages on this. Clean, readable, functional. A white page with a table and some coloured cells is fine. If using templates, something like Tailwind or even just minimal inline CSS is plenty.

---

## CLI Interface

The CLI is still the primary way to run fetches and scoring. The web UI is for viewing results.

Single entry point: `python score_emails.py`

### Arguments

| Flag | Description | Default |
|---|---|---|
| `fetch` | Fetch emails from HubSpot and insert into Postgres | — |
| `score` | Score all unscored emails in Postgres via Claude API | — |
| `serve` | Start the web UI server | — |
| `--start-date` | (fetch) Fetch emails from this date (YYYY-MM-DD) | None (all) |
| `--end-date` | (fetch) Fetch emails up to this date (YYYY-MM-DD) | None (today) |
| `-n, --count` | (fetch) Max emails to fetch from HubSpot | None (all) |
| `--batch-size` | (score) Concurrent Claude API requests | 5 |
| `--port` | (serve) Port for web UI | 8000 |
| `--export` | (any) Also dump results to `email_scores.xlsx` | False |

### Usage examples

```bash
# Fetch February emails
python score_emails.py fetch --start-date 2026-02-01 --end-date 2026-02-28

# Score everything that hasn't been scored yet
python score_emails.py score

# Start the dashboard
python score_emails.py serve

# Fetch, score, and export in one go
python score_emails.py fetch --start-date 2026-02-01 && python score_emails.py score --export
```

### Excel export

When `--export` is passed, also generate an `.xlsx` file with two sheets:

1. **Email Scores** — one row per email, colour-coded cells (green ≥8, yellow ≥6, orange ≥4, red <4)
2. **Rep Averages** — one row per rep, sorted by overall avg descending, same colour coding

Use `openpyxl`. Keep it clean — Arial font, frozen headers, auto-filters.

---

## Environment Setup

### Dependencies

```
anthropic
requests
python-dotenv
openpyxl
psycopg2-binary
fastapi
uvicorn
jinja2
```

### Database setup

Create the Postgres database and run the schema. Include a `schema.sql` file in the repo that can be run with:

```bash
createdb email_scores
psql email_scores < schema.sql
```

Or include a `python score_emails.py init-db` command that creates the tables if they don't exist.

### .env file

```
HUBSPOT_ACCESS=your_hubspot_token
ANTHROPIC_API_KEY=your_anthropic_key
DATABASE_URL=postgresql://user:pass@localhost:5432/email_scores
```

---

## Error Handling

- If Claude API returns a non-JSON response, retry once then mark that email with `score_error = true` in the `scores` table
- If HubSpot fetch fails partway, whatever was already inserted into Postgres is safe. Re-running `fetch` will skip existing emails (upsert on `id`).
- If an email has no `body_text` at all (null/empty), score it as all 1s automatically without calling Claude
- The scorer should only process emails with no row in `scores` — this makes it safe to re-run after partial failures
- Log all errors to stderr, don't crash the whole run for one bad email

---

## What's NOT in scope

- No auth/login on the web UI — it's internal only
- No scheduling/cron — manual CLI runs only
- No scoring of incoming emails — outgoing rep emails only
- No HubSpot write-back of scores
- No Docker — if deployed, it'll be Heroku, so keep things Heroku-friendly (Procfile, `DATABASE_URL` from env, single dyno)

---

## Files to reference

- `fetch_emails.py` — existing HubSpot fetch script, use as the basis for Module 1
- `feb_emails.json` — sample dataset of 100 emails for testing (available in project files)
- `email_scores.xlsx` — example of the desired Excel output format (already generated manually)

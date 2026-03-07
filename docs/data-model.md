# Data Model

PostgreSQL in production, async SQLite in tests. The async SQLAlchemy engine uses `asyncpg` as the driver. All tables include audit columns (`created_at`, `updated_at`, `created_by`, `updated_by`) via `AuditMixin`.

## Tables

### emails

Stores email data fetched from HubSpot.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | Integer | PK, auto-increment | |
| hubspot_id | String | NOT NULL | HubSpot email ID, used for upsert deduplication |
| timestamp | DateTime | | When the email was sent |
| from_name | String | | Sender display name |
| from_email | String | NOT NULL | Sender address |
| to_name | String | | Recipient display name |
| to_email | String | | Recipient address |
| subject | String | | Email subject line |
| body_text | Text | | Plain-text body |
| direction | String | | EMAIL, INCOMING_EMAIL, or FORWARDED_EMAIL |
| fetched_at | DateTime | | When the record was fetched from HubSpot |
| chain_id | Integer | FK -> email_chains.id, nullable | Links email to a conversation chain |
| position_in_chain | Integer | Nullable | Ordinal position within the chain (1-based) |
| open_count | Integer | Nullable | HubSpot engagement open count |
| click_count | Integer | Nullable | HubSpot engagement click count |
| reply_count | Integer | Nullable | HubSpot engagement reply count |
| message_id | String | Nullable | RFC 2822 Message-ID header |
| in_reply_to | String | Nullable | RFC 2822 In-Reply-To header |
| thread_id | String | Nullable | HubSpot thread identifier |

### scores

Claude API scoring results. One-to-one with emails (cascade delete).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | Integer | PK, auto-increment | |
| email_id | Integer | FK -> emails.id, UNIQUE | One score per email |
| personalisation | Integer | | 1-10 |
| clarity | Integer | | 1-10 |
| value_proposition | Integer | | 1-10 |
| cta | Integer | | 1-10 |
| overall | Integer | | 1-10, weighted average of the four dimensions |
| notes | Text | | Claude's brief explanation |
| score_error | Boolean | | True if scoring failed |
| scored_at | DateTime | | When the score was generated |

### email_chains

Groups related emails into conversation threads.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | Integer | PK, auto-increment | |
| normalized_subject | String | | Subject line with Re:/Fwd: prefixes stripped |
| participants | String | | Sorted comma-separated email addresses in the chain |
| started_at | DateTime | | Timestamp of the first email in the chain |
| last_activity_at | DateTime | | Timestamp of the most recent email in the chain |
| email_count | Integer | | Total emails in the chain |
| outgoing_count | Integer | | Outgoing emails in the chain |
| incoming_count | Integer | | Incoming emails in the chain |

### chain_scores

Conversation-level scoring results. One-to-one with email_chains (cascade delete).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | Integer | PK, auto-increment | |
| chain_id | Integer | FK -> email_chains.id, UNIQUE | One score per chain |
| progression | Integer | | 1-10. How well the conversation advances toward the sales goal |
| responsiveness | Integer | | 1-10. Timeliness and relevance of follow-ups |
| persistence | Integer | | 1-10. Appropriate follow-up cadence |
| conversation_quality | Integer | | 1-10. Overall multi-touch engagement quality |
| avg_response_hours | Float | Nullable | Average response time in hours |
| notes | Text | Nullable | Claude's explanation of the chain scores |
| score_error | Boolean | | True if scoring failed |
| scored_at | DateTime | | When the score was generated |

### reps

Canonical rep identities for name normalisation and team aggregation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| email | String | PK | Canonical email address |
| display_name | String | | Normalised display name |

### settings

Single-row application configuration. Seeded on first migration.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | Integer | PK, CHECK (id = 1) | Always 1 |
| global_start_date | Date | | Floor for all fetches. Default 2025-09-01 |
| company_domains | String | | Comma-separated domains for outgoing email filtering |
| scoring_batch_size | Integer | | Concurrency limit for Claude API calls. Default 5 |
| auto_score_after_fetch | Boolean | | When true, fetch also scores unscored emails. Default true |
| initial_email_prompt | Text | | Configurable prompt for individual email scoring. Defaults to four-dimension scoring prompt (personalisation, clarity, value_proposition, cta) |
| chain_email_prompt | Text | | Prompt for scoring emails within a conversation chain context |
| chain_evaluation_prompt | Text | | Prompt for evaluating conversation chains (progression, responsiveness, persistence, conversation_quality) |
| weight_value_proposition | Float | | Weight for value_proposition in overall score calculation. Default 0.35 |
| weight_personalisation | Float | | Weight for personalisation in overall score calculation. Default 0.30 |
| weight_cta | Float | | Weight for cta in overall score calculation. Default 0.20 |
| weight_clarity | Float | | Weight for clarity in overall score calculation. Default 0.15 |

### jobs

Operation execution history.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| job_id | Integer | PK, auto-increment | |
| job_type | String | | FETCH, SCORE, RESCORE, EXPORT, or CHAIN_BUILD |
| status | String | | PENDING, RUNNING, COMPLETED, or FAILED |
| started_at | DateTime | | Set when status becomes RUNNING |
| completed_at | DateTime | | Set when status becomes COMPLETED or FAILED |
| result_summary | JSON | | Operation-specific results (e.g. fetched count, scored count) |
| error_message | Text | | Error details on FAILED status |
| triggered_by | String | | "cron" or "ui" |

## Relationships

```
┌──────────────┐       ┌──────────────┐
│  EmailChain  │───1:N─│    Email     │
│              │       │              │
│  id (PK)     │       │  chain_id(FK)│
└──────┬───────┘       └──────┬───────┘
       │                      │
       │ 1:1                  │ 1:1
       │                      │
┌──────┴───────┐       ┌──────┴───────┐
│  ChainScore  │       │    Score     │
│              │       │              │
│  chain_id(FK)│       │  email_id(FK)│
└──────────────┘       └──────────────┘
```

- **EmailChain -> Email**: one-to-many. Emails reference their chain via `chain_id`. An email's `position_in_chain` gives its ordinal position (1-based, by timestamp).
- **EmailChain -> ChainScore**: one-to-one, cascade delete. Deleting a chain removes its chain_score.
- **Email -> Score**: one-to-one, cascade delete. Deleting an email removes its score.
- **Rep** averages are computed as queries, not materialised — the dataset is small enough.

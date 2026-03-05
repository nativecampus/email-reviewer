# Email Reviewer

Automated scoring system for outgoing sales rep emails. Fetches emails from HubSpot, scores them against a rubric using the Claude API, and displays results through a web dashboard.

## Quick Start

```bash
pipenv install --dev
cp .env.example .env            # fill in credentials
createdb email_reviewer
pipenv run alembic upgrade head
pipenv run uvicorn app.main:app --reload --port 8000
```

See [docs/development.md](docs/development.md) for full setup instructions.

## How It Works

1. **Fetch** - Pull outgoing sales emails from HubSpot, filter to rep domains, upsert into PostgreSQL
2. **Score** - Send unscored emails to Claude API, evaluate against a 5-criteria rubric (personalisation, clarity, value proposition, CTA, overall), store results
3. **View** - Web dashboard showing rep team and individual email scores

## Tech Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL with async SQLAlchemy and Alembic migrations
- **Scoring**: Anthropic Claude API
- **Email source**: HubSpot CRM v3 API
- **Deployment**: Heroku (single web dyno)

## Documentation

| Document | Contents |
|----------|----------|
| [Architecture](docs/architecture.md) | System design, data pipeline, database schema, key decisions |
| [Development](docs/development.md) | Prerequisites, local setup, seeding, running tests, migrations, CI/CD, deployment, project structure |
| [Coding Standards](docs/coding_standards.md) | Patterns and conventions for coding agents |
| [Testing Guide](docs/testing-guide.md) | What to test, what not to test, stack-specific guidance |
| [Visual Testing](docs/visual-testing.md) | Selenium screenshot testing for UI changes |

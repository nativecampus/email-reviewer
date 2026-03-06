"""Score unscored emails using the Claude API."""

import asyncio
import json
import logging
from datetime import datetime

from anthropic import AsyncAnthropic, RateLimitError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.email import Email
from app.models.score import Score
from app.schemas.score import ScoringResult

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """You are an expert sales email evaluator. Score the following outgoing sales email on five dimensions, each from 1 (worst) to 10 (best):

1. **personalisation** - How tailored is the email to the specific recipient? Does it reference their company, role, recent activity, or pain points?
2. **clarity** - Is the message easy to read and understand? Is it concise with a clear structure?
3. **value_proposition** - Does the email clearly articulate what value the sender offers to the recipient?
4. **cta** - Is there a clear, specific call to action? Is it easy for the recipient to take the next step?
5. **overall** - Holistic quality of the email as a sales outreach message.

Respond with ONLY a JSON object in this exact format, no other text:
{
  "personalisation": <1-10>,
  "clarity": <1-10>,
  "value_proposition": <1-10>,
  "cta": <1-10>,
  "overall": <1-10>,
  "notes": "<brief 1-2 sentence explanation of the scores>"
}"""

MAX_BODY_LENGTH = 4000
MIN_WORD_COUNT = 20
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER = 60


def _build_user_message(email: Email) -> str:
    """Format email metadata and body into a prompt string for Claude."""
    body = email.body_text or ""
    if len(body) > MAX_BODY_LENGTH:
        body = body[:MAX_BODY_LENGTH]

    date_str = str(email.timestamp) if email.timestamp else ""

    from_parts = [email.from_name, email.from_email]
    from_str = " ".join(p for p in from_parts if p)

    to_parts = [email.to_name, email.to_email]
    to_str = " ".join(p for p in to_parts if p)

    return (
        f"From: {from_str}\n"
        f"To: {to_str}\n"
        f"Subject: {email.subject or ''}\n"
        f"Date: {date_str}\n"
        f"Body:\n{body}"
    )


def _get_retry_after(exc: RateLimitError) -> float:
    """Extract retry-after seconds from a RateLimitError's response headers."""
    try:
        return float(exc.response.headers["retry-after"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


async def _call_claude_with_retry(
    client: AsyncAnthropic, user_message: str
) -> tuple[object, dict]:
    """Call Claude API, retrying on 429 using the retry-after header.

    Returns (response, token_totals). Raises RateLimitError if all retries
    are exhausted.
    """
    total_tokens = {"input": 0, "output": 0}

    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=SCORING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            total_tokens["input"] += response.usage.input_tokens
            total_tokens["output"] += response.usage.output_tokens
            return response, total_tokens
        except RateLimitError as exc:
            if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                raise
            delay = _get_retry_after(exc)
            logger.warning(
                "Rate limited by Claude API, retry-after %gs (attempt %d/%d)",
                delay, attempt + 1, MAX_RATE_LIMIT_RETRIES,
            )
            await asyncio.sleep(delay)

    # Unreachable, but keeps the type checker happy
    raise RateLimitError(message="Rate limit retries exhausted", response=None, body=None)


async def _score_single_email(
    client: AsyncAnthropic, email: Email, semaphore: asyncio.Semaphore
) -> ScoringResult | None:
    """Call Claude to score one email. Retry once on parse failure.

    Retries with exponential backoff on rate limit (429) errors.
    Returns a ScoringResult on success or None if both parse attempts fail.
    """
    user_message = _build_user_message(email)

    async with semaphore:
        for _attempt in range(2):
            try:
                response, total_tokens = await _call_claude_with_retry(
                    client, user_message
                )
            except RateLimitError:
                return None

            try:
                raw = json.loads(response.content[0].text)
                result = ScoringResult(**raw)
                result._tokens = total_tokens
                return result
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

    return None


async def score_unscored_emails(
    session: AsyncSession, batch_size: int = 5
) -> dict:
    """Score emails that don't yet have a score record.

    Emails with empty or very short bodies (under 20 words) are skipped
    entirely — no score row is created since there is no content to
    evaluate. Returns a summary dict with counts and total tokens used.
    """
    # Find emails without a score via LEFT JOIN
    stmt = (
        select(Email)
        .outerjoin(Score, Email.id == Score.email_id)
        .where(Score.id.is_(None))
    )
    result = await session.execute(stmt)
    unscored = result.scalars().all()

    summary = {
        "total_unscored": len(unscored),
        "scored": 0,
        "skipped": 0,
        "errors": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    to_score_with_claude = []

    for email in unscored:
        body = email.body_text or ""
        word_count = len(body.split()) if body.strip() else 0

        if not body.strip() or word_count < MIN_WORD_COUNT:
            summary["skipped"] += 1
        else:
            to_score_with_claude.append(email)

    if to_score_with_claude:
        client = AsyncAnthropic()
        semaphore = asyncio.Semaphore(batch_size)

        tasks = [
            _score_single_email(client, email, semaphore)
            for email in to_score_with_claude
        ]
        results = await asyncio.gather(*tasks)

        for email, scoring_result in zip(to_score_with_claude, results):
            if scoring_result is not None:
                tokens = getattr(scoring_result, "_tokens", {})
                score = Score(
                    email_id=email.id,
                    personalisation=scoring_result.personalisation,
                    clarity=scoring_result.clarity,
                    value_proposition=scoring_result.value_proposition,
                    cta=scoring_result.cta,
                    notes=scoring_result.notes,
                    score_error=False,
                    scored_at=datetime.utcnow(),
                )
                session.add(score)
                summary["scored"] += 1
                summary["total_input_tokens"] += tokens.get("input", 0)
                summary["total_output_tokens"] += tokens.get("output", 0)
            else:
                score = Score(
                    email_id=email.id,
                    score_error=True,
                    scored_at=datetime.utcnow(),
                )
                session.add(score)
                summary["errors"] += 1

    await session.flush()
    return summary

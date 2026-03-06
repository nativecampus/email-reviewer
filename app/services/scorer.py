"""Score unscored emails and conversation chains using the Claude API."""

import asyncio
import json
import logging
import math
from datetime import datetime

from anthropic import AsyncAnthropic, RateLimitError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.chain import EmailChain
from app.models.chain_score import ChainScore
from app.models.email import Email
from app.models.score import Score
from app.models.settings import Settings
from app.schemas.chain_score import ChainScoringResult
from app.schemas.score import ScoringResult
from app.services.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_PROMPT = """You are an expert sales email evaluator. Score the following outgoing sales email on five dimensions, each from 1 (worst) to 10 (best):

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
MAX_CHAIN_EMAIL_LENGTH = 2000
MIN_WORD_COUNT = 20
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_AFTER = 60


def _calculate_weighted_overall(scores: dict, weights: dict) -> int:
    """Compute weighted sum of the 4 dimensions. Round to nearest int, clamp 1-10."""
    weighted = (
        scores["value_proposition"] * weights["weight_value_proposition"]
        + scores["personalisation"] * weights["weight_personalisation"]
        + scores["cta"] * weights["weight_cta"]
        + scores["clarity"] * weights["weight_clarity"]
    )
    rounded = math.floor(weighted + 0.5)
    return max(1, min(10, rounded))


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

    parts = []

    # Include chain context for follow-up emails
    chain_context = getattr(email, "_chain_context", None)
    if chain_context and (email.position_in_chain or 0) > 1:
        parts.append(f"Previous conversation:\n{chain_context}\n")

    parts.append(
        f"From: {from_str}\n"
        f"To: {to_str}\n"
        f"Subject: {email.subject or ''}\n"
        f"Date: {date_str}\n"
        f"Body:\n{body}"
    )

    return "\n".join(parts)


async def _build_chain_context(session: AsyncSession, email: Email) -> str:
    """Build context from prior emails in the same chain.

    Returns empty string when the email has no chain or is the first in its chain.
    Each prior email body is truncated to 2000 characters.
    """
    if email.chain_id is None or (email.position_in_chain or 0) <= 1:
        return ""

    stmt = (
        select(Email)
        .where(Email.chain_id == email.chain_id)
        .where(Email.position_in_chain < email.position_in_chain)
        .order_by(Email.position_in_chain)
    )
    result = await session.execute(stmt)
    prior_emails = result.scalars().all()

    if not prior_emails:
        return ""

    sections = []
    for prior in prior_emails:
        body = prior.body_text or ""
        if len(body) > MAX_CHAIN_EMAIL_LENGTH:
            body = body[:MAX_CHAIN_EMAIL_LENGTH]

        from_parts = [prior.from_name, prior.from_email]
        from_str = " ".join(p for p in from_parts if p)
        to_parts = [prior.to_name, prior.to_email]
        to_str = " ".join(p for p in to_parts if p)
        date_str = str(prior.timestamp) if prior.timestamp else ""

        sections.append(
            f"From: {from_str}\n"
            f"To: {to_str}\n"
            f"Date: {date_str}\n"
            f"Subject: {prior.subject or ''}\n"
            f"Body: {body}"
        )

    return "\n---\n".join(sections)


def _get_retry_after(exc: RateLimitError) -> float:
    """Extract retry-after seconds from a RateLimitError's response headers."""
    try:
        return float(exc.response.headers["retry-after"])
    except (AttributeError, KeyError, TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


async def _call_claude_with_retry(
    client: AsyncAnthropic, user_message: str, system_prompt: str
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
                system=system_prompt,
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
    client: AsyncAnthropic,
    email: Email,
    semaphore: asyncio.Semaphore,
    settings: Settings,
) -> ScoringResult | None:
    """Call Claude to score one email. Retry once on parse failure.

    Retries with exponential backoff on rate limit (429) errors.
    Returns a ScoringResult on success or None if both parse attempts fail.
    """
    # Build chain context for follow-up emails
    chain_context = getattr(email, "_chain_context", "")
    if chain_context and (email.position_in_chain or 0) > 1:
        pass  # already set
    email._chain_context = chain_context

    user_message = _build_user_message(email)

    # Choose prompt based on chain position
    if email.chain_id is not None and (email.position_in_chain or 0) > 1:
        system_prompt = settings.chain_email_prompt
    else:
        system_prompt = settings.initial_email_prompt

    async with semaphore:
        for _attempt in range(2):
            try:
                response, total_tokens = await _call_claude_with_retry(
                    client, user_message, system_prompt
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
        settings = await get_settings(session)

        weights = {
            "weight_value_proposition": settings.weight_value_proposition,
            "weight_personalisation": settings.weight_personalisation,
            "weight_cta": settings.weight_cta,
            "weight_clarity": settings.weight_clarity,
        }

        # Pre-build chain context for follow-up emails
        for email in to_score_with_claude:
            email._chain_context = await _build_chain_context(session, email)

        tasks = [
            _score_single_email(client, email, semaphore, settings)
            for email in to_score_with_claude
        ]
        results = await asyncio.gather(*tasks)

        for email, scoring_result in zip(to_score_with_claude, results):
            if scoring_result is not None:
                tokens = getattr(scoring_result, "_tokens", {})
                dimension_scores = {
                    "value_proposition": scoring_result.value_proposition,
                    "personalisation": scoring_result.personalisation,
                    "cta": scoring_result.cta,
                    "clarity": scoring_result.clarity,
                }
                overall = _calculate_weighted_overall(dimension_scores, weights)
                score = Score(
                    email_id=email.id,
                    personalisation=scoring_result.personalisation,
                    clarity=scoring_result.clarity,
                    value_proposition=scoring_result.value_proposition,
                    cta=scoring_result.cta,
                    overall=overall,
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

    # Score unscored chains after individual emails
    chain_result = await score_unscored_chains(session, batch_size=batch_size)
    summary["chains_scored"] = chain_result["chains_scored"]
    summary["chain_errors"] = chain_result["errors"]
    summary["total_input_tokens"] += chain_result["total_input_tokens"]
    summary["total_output_tokens"] += chain_result["total_output_tokens"]

    return summary


def _compute_avg_response_hours(emails: list[Email]) -> float | None:
    """Compute average hours between consecutive outgoing emails."""
    outgoing = [
        e for e in sorted(emails, key=lambda e: e.position_in_chain or 0)
        if e.direction == "EMAIL" and e.timestamp is not None
    ]
    if len(outgoing) < 2:
        return None

    deltas = []
    for i in range(1, len(outgoing)):
        delta = (outgoing[i].timestamp - outgoing[i - 1].timestamp).total_seconds() / 3600
        deltas.append(delta)

    return sum(deltas) / len(deltas) if deltas else None


async def score_unscored_chains(
    session: AsyncSession, batch_size: int = 5
) -> dict:
    """Score chains that don't yet have a chain_score record.

    Only chains with email_count >= 2 are scored. Returns a summary dict.
    """
    stmt = (
        select(EmailChain)
        .outerjoin(ChainScore, EmailChain.id == ChainScore.chain_id)
        .where(ChainScore.id.is_(None))
        .where(EmailChain.email_count >= 2)
    )
    result = await session.execute(stmt)
    unscored_chains = result.scalars().all()

    summary = {
        "chains_scored": 0,
        "errors": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }

    if not unscored_chains:
        return summary

    settings = await get_settings(session)
    client = AsyncAnthropic()

    for chain in unscored_chains:
        # Fetch all emails in this chain
        email_stmt = (
            select(Email)
            .where(Email.chain_id == chain.id)
            .order_by(Email.position_in_chain)
        )
        email_result = await session.execute(email_stmt)
        chain_emails = email_result.scalars().all()

        # Build conversation context
        sections = []
        for email in chain_emails:
            body = email.body_text or ""
            if len(body) > MAX_CHAIN_EMAIL_LENGTH:
                body = body[:MAX_CHAIN_EMAIL_LENGTH]

            from_parts = [email.from_name, email.from_email]
            from_str = " ".join(p for p in from_parts if p)
            to_parts = [email.to_name, email.to_email]
            to_str = " ".join(p for p in to_parts if p)
            date_str = str(email.timestamp) if email.timestamp else ""

            sections.append(
                f"From: {from_str}\n"
                f"To: {to_str}\n"
                f"Date: {date_str}\n"
                f"Subject: {email.subject or ''}\n"
                f"Body: {body}"
            )

        conversation_text = "\n---\n".join(sections)

        avg_hours = _compute_avg_response_hours(chain_emails)

        # Call Claude with chain evaluation prompt
        scoring_result = None
        total_tokens = {"input": 0, "output": 0}

        for _attempt in range(2):
            try:
                response = await client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    system=settings.chain_evaluation_prompt,
                    messages=[{"role": "user", "content": conversation_text}],
                )
                total_tokens["input"] += response.usage.input_tokens
                total_tokens["output"] += response.usage.output_tokens
            except RateLimitError:
                break

            try:
                raw = json.loads(response.content[0].text)
                scoring_result = ChainScoringResult(**raw)
                break
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

        if scoring_result is not None:
            chain_score = ChainScore(
                chain_id=chain.id,
                progression=scoring_result.progression,
                responsiveness=scoring_result.responsiveness,
                persistence=scoring_result.persistence,
                conversation_quality=scoring_result.conversation_quality,
                avg_response_hours=avg_hours,
                notes=scoring_result.notes,
                score_error=False,
                scored_at=datetime.utcnow(),
            )
            session.add(chain_score)
            summary["chains_scored"] += 1
        else:
            chain_score = ChainScore(
                chain_id=chain.id,
                score_error=True,
                scored_at=datetime.utcnow(),
            )
            session.add(chain_score)
            summary["errors"] += 1

        summary["total_input_tokens"] += total_tokens["input"]
        summary["total_output_tokens"] += total_tokens["output"]

    await session.flush()
    return summary

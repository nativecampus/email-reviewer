"""Job runners for fetch, score, rescore, and export operations."""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_config
from app.enums import JobStatus, JobType
from app.models.email import Email
from app.models.job import Job
from app.models.score import Score
from app.services.export import export_to_excel
from app.services.fetcher import fetch_and_store
from app.services.scorer import score_unscored_emails
from app.services.settings import get_settings


def _set_running(job: Job) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)


def _set_completed(job: Job, result_summary: dict) -> None:
    job.status = JobStatus.COMPLETED
    job.completed_at = datetime.now(timezone.utc)
    job.result_summary = result_summary


def _set_failed(job: Job, error: str) -> None:
    job.status = JobStatus.FAILED
    job.completed_at = datetime.now(timezone.utc)
    job.error_message = error


async def run_fetch_job(session: AsyncSession, job_id: int) -> None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one()
    _set_running(job)
    await session.flush()

    try:
        settings = await get_settings(session)
        company_domains = [
            d.strip() for d in settings.company_domains.split(",") if d.strip()
        ]

        # Compute effective start date
        max_fetched = await session.execute(select(func.max(Email.fetched_at)))
        max_fetched_at = max_fetched.scalar_one_or_none()

        global_start = datetime.combine(
            settings.global_start_date, datetime.min.time()
        )
        if max_fetched_at and max_fetched_at > global_start:
            effective_start = max_fetched_at
        else:
            effective_start = global_start

        fetched_count = await fetch_and_store(
            session,
            access_token=app_config.HUBSPOT_ACCESS_TOKEN,
            company_domains=company_domains,
            start_date=effective_start,
        )

        # Count new reps created in this session
        new_reps_result = await session.execute(
            select(func.count()).select_from(
                select(Email.from_email)
                .distinct()
                .where(Email.fetched_at.isnot(None))
                .subquery()
            )
        )
        new_reps_count = new_reps_result.scalar_one()

        summary: dict = {"fetched": fetched_count, "new_reps": new_reps_count}

        if settings.auto_score_after_fetch:
            score_result = await score_unscored_emails(
                session, batch_size=settings.scoring_batch_size
            )
            summary["scored"] = score_result.get("scored", 0) + score_result.get(
                "auto_scored", 0
            )
            summary["errors"] = score_result.get("errors", 0)
            summary["tokens"] = score_result.get(
                "total_input_tokens", 0
            ) + score_result.get("total_output_tokens", 0)

        _set_completed(job, summary)
        await session.flush()

    except Exception as exc:
        _set_failed(job, str(exc))
        await session.flush()


async def run_score_job(session: AsyncSession, job_id: int) -> None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one()
    _set_running(job)
    await session.flush()

    try:
        settings = await get_settings(session)
        score_result = await score_unscored_emails(
            session, batch_size=settings.scoring_batch_size
        )
        summary = {
            "scored": score_result.get("scored", 0)
            + score_result.get("auto_scored", 0),
            "errors": score_result.get("errors", 0),
            "tokens": score_result.get("total_input_tokens", 0)
            + score_result.get("total_output_tokens", 0),
        }
        _set_completed(job, summary)
        await session.flush()

    except Exception as exc:
        _set_failed(job, str(exc))
        await session.flush()


async def run_rescore_job(session: AsyncSession, job_id: int) -> None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one()
    _set_running(job)
    await session.flush()

    try:
        # Delete all existing scores
        await session.execute(delete(Score))
        await session.flush()

        settings = await get_settings(session)
        score_result = await score_unscored_emails(
            session, batch_size=settings.scoring_batch_size
        )
        summary = {
            "scored": score_result.get("scored", 0)
            + score_result.get("auto_scored", 0),
            "errors": score_result.get("errors", 0),
            "tokens": score_result.get("total_input_tokens", 0)
            + score_result.get("total_output_tokens", 0),
        }
        _set_completed(job, summary)
        await session.flush()

    except Exception as exc:
        _set_failed(job, str(exc))
        await session.flush()


async def run_export_job(
    session: AsyncSession, job_id: int, output_path: str = "export.xlsx"
) -> None:
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one()
    _set_running(job)
    await session.flush()

    try:
        path = await export_to_excel(session, output_path)
        _set_completed(job, {"output_path": path})
        await session.flush()

    except Exception as exc:
        _set_failed(job, str(exc))
        await session.flush()

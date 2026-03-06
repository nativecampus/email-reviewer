"""Job runners for fetch, score, rescore, and export operations."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_config
from app.models.base import _utcnow
from app.database import worker_session
from app.enums import JobStatus, JobType
from app.models.email import Email
from app.models.job import Job
from app.models.score import Score
from app.services.export import export_to_excel
from app.services.fetcher import fetch_and_store
from app.services.scorer import score_unscored_emails
from app.services.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session_scope(session: Optional[AsyncSession] = None):
    """Yield the provided session or create a new one, committing on exit.

    When session is None (RQ worker), creates a fresh engine and session via
    worker_session() to avoid event loop mismatch with the module-level engine.
    """
    if session is not None:
        yield session
        await session.commit()
    else:
        async with worker_session() as new_session:
            yield new_session
            await new_session.commit()


def _set_running(job: Job) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = _utcnow()


def _set_completed(job: Job, result_summary: dict) -> None:
    job.status = JobStatus.COMPLETED
    job.completed_at = _utcnow()
    job.result_summary = result_summary


def _set_failed(job: Job, error: str) -> None:
    job.status = JobStatus.FAILED
    job.completed_at = _utcnow()
    job.error_message = error


async def _fail_job(session: AsyncSession, job_id: int, exc: Exception) -> None:
    """Record a job failure, handling cases where the session may be dirty.

    Rolls back any pending changes, then loads the job fresh and sets FAILED.
    If even the failure recording fails (e.g. DB unreachable), logs the error
    so it's visible in worker output.
    """
    error_msg = str(exc)
    try:
        await session.rollback()
        result = await session.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        _set_failed(job, error_msg)
        await session.flush()
    except Exception as inner:
        logger.error(
            "Job %d failed with: %s. Additionally failed to record error: %s",
            job_id, error_msg, inner,
        )


async def run_fetch_job(
    session: Optional[AsyncSession],
    job_id: int,
    *,
    fetch_start_date: Optional[date] = None,
    fetch_end_date: Optional[date] = None,
    max_count: Optional[int] = None,
    auto_score: Optional[bool] = None,
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.flush()

            settings = await get_settings(s)
            company_domains = [
                d.strip() for d in settings.company_domains.split(",") if d.strip()
            ]

            # Compute effective start date
            if fetch_start_date:
                effective_start = datetime.combine(
                    fetch_start_date, datetime.min.time()
                )
            else:
                max_fetched = await s.execute(select(func.max(Email.fetched_at)))
                max_fetched_at = max_fetched.scalar_one_or_none()

                global_start = datetime.combine(
                    settings.global_start_date, datetime.min.time()
                )
                if max_fetched_at and max_fetched_at > global_start:
                    effective_start = max_fetched_at
                else:
                    effective_start = global_start

            fetch_kwargs: dict = {
                "start_date": effective_start,
            }
            if fetch_end_date:
                fetch_kwargs["end_date"] = datetime.combine(
                    fetch_end_date, datetime.min.time()
                )
            if max_count is not None:
                fetch_kwargs["max_count"] = max_count

            fetched_count = await fetch_and_store(
                s,
                access_token=app_config.HUBSPOT_ACCESS_TOKEN,
                company_domains=company_domains,
                **fetch_kwargs,
            )

            # Count new reps created in this session
            new_reps_result = await s.execute(
                select(func.count()).select_from(
                    select(Email.from_email)
                    .distinct()
                    .where(Email.fetched_at.isnot(None))
                    .subquery()
                )
            )
            new_reps_count = new_reps_result.scalar_one()

            summary: dict = {"fetched": fetched_count, "new_reps": new_reps_count}

            should_score = auto_score if auto_score is not None else settings.auto_score_after_fetch
            if should_score:
                score_result = await score_unscored_emails(
                    s, batch_size=settings.scoring_batch_size
                )
                summary["scored"] = score_result.get("scored", 0) + score_result.get(
                    "auto_scored", 0
                )
                summary["errors"] = score_result.get("errors", 0)
                summary["tokens"] = score_result.get(
                    "total_input_tokens", 0
                ) + score_result.get("total_output_tokens", 0)

            _set_completed(job, summary)
            await s.flush()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_score_job(
    session: Optional[AsyncSession], job_id: int
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.flush()

            settings = await get_settings(s)
            score_result = await score_unscored_emails(
                s, batch_size=settings.scoring_batch_size
            )
            summary = {
                "scored": score_result.get("scored", 0)
                + score_result.get("auto_scored", 0),
                "errors": score_result.get("errors", 0),
                "tokens": score_result.get("total_input_tokens", 0)
                + score_result.get("total_output_tokens", 0),
            }
            _set_completed(job, summary)
            await s.flush()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_rescore_job(
    session: Optional[AsyncSession], job_id: int
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.flush()

            # Delete all existing scores
            await s.execute(delete(Score))
            await s.flush()

            settings = await get_settings(s)
            score_result = await score_unscored_emails(
                s, batch_size=settings.scoring_batch_size
            )
            summary = {
                "scored": score_result.get("scored", 0)
                + score_result.get("auto_scored", 0),
                "errors": score_result.get("errors", 0),
                "tokens": score_result.get("total_input_tokens", 0)
                + score_result.get("total_output_tokens", 0),
            }
            _set_completed(job, summary)
            await s.flush()

        except Exception as exc:
            await _fail_job(s, job_id, exc)


async def run_export_job(
    session: Optional[AsyncSession],
    job_id: int,
    output_path: str = "export.xlsx",
) -> None:
    async with _session_scope(session) as s:
        try:
            result = await s.execute(select(Job).where(Job.job_id == job_id))
            job = result.scalar_one()
            _set_running(job)
            await s.flush()

            path = await export_to_excel(s, output_path)
            _set_completed(job, {"output_path": path})
            await s.flush()

        except Exception as exc:
            await _fail_job(s, job_id, exc)

"""Synchronous RQ task wrappers that call async job runners via asyncio.run()."""

import asyncio
import logging
from datetime import date
from typing import Optional

from app.services.job_runner import (
    run_export_job,
    run_fetch_job,
    run_rescore_job,
    run_score_job,
)

logger = logging.getLogger(__name__)


def _run_with_error_handling(coro, job_id: int, job_type: str) -> None:
    """Run an async job runner, recording failure if the coroutine raises.

    The job runners handle their own exceptions internally. This outer handler
    catches failures that escape the runner (e.g. session creation failure)
    and attempts to mark the job as FAILED via a fresh database connection.
    """
    try:
        asyncio.run(coro)
    except Exception as exc:
        logger.error("RQ task %s (job %d) failed: %s", job_type, job_id, exc)
        try:
            asyncio.run(_record_failure(job_id, str(exc)))
        except Exception as inner:
            logger.error(
                "Failed to record error for job %d: %s", job_id, inner
            )


async def _record_failure(job_id: int, error: str) -> None:
    """Last-resort failure recording using a fresh engine and session."""
    from app.database import worker_session
    from app.enums import JobStatus
    from app.models.base import _utcnow
    from app.models.job import Job
    from sqlalchemy import select

    async with worker_session() as session:
        result = await session.execute(select(Job).where(Job.job_id == job_id))
        job = result.scalar_one()
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            job.status = JobStatus.FAILED
            job.completed_at = _utcnow()
            job.error_message = error
        await session.commit()


def fetch_task(
    job_id: int,
    *,
    fetch_start_date: Optional[date] = None,
    fetch_end_date: Optional[date] = None,
    max_count: Optional[int] = None,
    auto_score: Optional[bool] = None,
) -> None:
    """RQ-compatible synchronous wrapper for run_fetch_job."""
    _run_with_error_handling(
        run_fetch_job(
            None,
            job_id,
            fetch_start_date=fetch_start_date,
            fetch_end_date=fetch_end_date,
            max_count=max_count,
            auto_score=auto_score,
        ),
        job_id,
        "FETCH",
    )


def score_task(job_id: int) -> None:
    """RQ-compatible synchronous wrapper for run_score_job."""
    _run_with_error_handling(
        run_score_job(None, job_id),
        job_id,
        "SCORE",
    )


def rescore_task(job_id: int) -> None:
    """RQ-compatible synchronous wrapper for run_rescore_job."""
    _run_with_error_handling(
        run_rescore_job(None, job_id),
        job_id,
        "RESCORE",
    )


def export_task(job_id: int, output_path: str = "export.xlsx") -> None:
    """RQ-compatible synchronous wrapper for run_export_job."""
    _run_with_error_handling(
        run_export_job(None, job_id, output_path),
        job_id,
        "EXPORT",
    )

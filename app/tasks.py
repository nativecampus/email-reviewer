"""Synchronous RQ task wrappers that call async job runners via asyncio.run()."""

import asyncio
from datetime import date
from typing import Optional

from app.services.job_runner import (
    run_export_job,
    run_fetch_job,
    run_rescore_job,
    run_score_job,
)


def fetch_task(
    job_id: int,
    *,
    fetch_start_date: Optional[date] = None,
    fetch_end_date: Optional[date] = None,
    max_count: Optional[int] = None,
) -> None:
    """RQ-compatible synchronous wrapper for run_fetch_job."""
    asyncio.run(
        run_fetch_job(
            None,
            job_id,
            fetch_start_date=fetch_start_date,
            fetch_end_date=fetch_end_date,
            max_count=max_count,
        )
    )


def score_task(job_id: int) -> None:
    """RQ-compatible synchronous wrapper for run_score_job."""
    asyncio.run(run_score_job(None, job_id))


def rescore_task(job_id: int) -> None:
    """RQ-compatible synchronous wrapper for run_rescore_job."""
    asyncio.run(run_rescore_job(None, job_id))


def export_task(job_id: int, output_path: str = "export.xlsx") -> None:
    """RQ-compatible synchronous wrapper for run_export_job."""
    asyncio.run(run_export_job(None, job_id, output_path))

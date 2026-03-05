from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import JobStatus, JobType
from app.models.job import Job
from app.schemas.job import FetchRequest, JobResponse, LastRunResponse
from app.services.job_runner import (
    run_export_job,
    run_fetch_job,
    run_rescore_job,
    run_score_job,
)
from app.tasks import export_task, fetch_task, rescore_task, score_task
from app.worker import get_queue, validate_redis

router = APIRouter(prefix="/api/operations")


async def _check_no_running(
    session: AsyncSession, job_types: list[str]
) -> None:
    """Raise 409 if any job of the given types is currently RUNNING."""
    stmt = (
        select(Job)
        .where(Job.job_type.in_(job_types))
        .where(Job.status == JobStatus.RUNNING)
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A conflicting job is already running",
        )


async def _create_job(
    session: AsyncSession, job_type: str, triggered_by: str = "ui"
) -> Job:
    job = Job(job_type=job_type, status=JobStatus.PENDING, triggered_by=triggered_by)
    session.add(job)
    await session.flush()
    return job


def _validate_queue():
    """Return the RQ Queue if Redis is configured, or None for BackgroundTasks fallback.

    Raises 503 if Redis is configured but unhealthy (unreachable or no workers).
    """
    error = validate_redis()
    if error:
        raise HTTPException(status_code=503, detail=error)
    return get_queue()


@router.post("/fetch", status_code=202, response_model=JobResponse)
async def start_fetch(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    body: Optional[FetchRequest] = Body(default=None),
):
    queue = _validate_queue()
    await _check_no_running(session, [JobType.FETCH])
    job = await _create_job(session, JobType.FETCH)

    fetch_kwargs: dict = {}
    if body:
        params = {
            "start_date": body.start_date.isoformat() if body.start_date else None,
            "end_date": body.end_date.isoformat() if body.end_date else None,
            "max_count": body.max_count,
        }
        job.result_summary = {"params": params}
        if body.start_date:
            fetch_kwargs["fetch_start_date"] = body.start_date
        if body.end_date:
            fetch_kwargs["fetch_end_date"] = body.end_date
        if body.max_count is not None:
            fetch_kwargs["max_count"] = body.max_count

    await session.commit()

    if queue is not None:
        queue.enqueue(fetch_task, job.job_id, **fetch_kwargs)
    else:
        background_tasks.add_task(run_fetch_job, None, job.job_id, **fetch_kwargs)
    return job


@router.post("/score", status_code=202, response_model=JobResponse)
async def start_score(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    queue = _validate_queue()
    await _check_no_running(session, [JobType.SCORE, JobType.RESCORE])
    job = await _create_job(session, JobType.SCORE)
    await session.commit()

    if queue is not None:
        queue.enqueue(score_task, job.job_id)
    else:
        background_tasks.add_task(run_score_job, None, job.job_id)
    return job


@router.post("/rescore", status_code=202, response_model=JobResponse)
async def start_rescore(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    queue = _validate_queue()
    await _check_no_running(session, [JobType.SCORE, JobType.RESCORE])
    job = await _create_job(session, JobType.RESCORE)
    await session.commit()

    if queue is not None:
        queue.enqueue(rescore_task, job.job_id)
    else:
        background_tasks.add_task(run_rescore_job, None, job.job_id)
    return job


@router.post("/export", status_code=202, response_model=JobResponse)
async def start_export(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    queue = _validate_queue()
    job = await _create_job(session, JobType.EXPORT)
    await session.commit()

    if queue is not None:
        queue.enqueue(export_task, job.job_id)
    else:
        background_tasks.add_task(run_export_job, None, job.job_id)
    return job


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Job).order_by(Job.created_at.desc())
    )
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/last-run", response_model=LastRunResponse)
async def last_run(session: AsyncSession = Depends(get_db)):
    response = {}
    for jt in [JobType.FETCH, JobType.SCORE, JobType.RESCORE, JobType.EXPORT]:
        stmt = (
            select(Job)
            .where(Job.job_type == jt)
            .where(Job.status == JobStatus.COMPLETED)
            .order_by(Job.completed_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        response[jt.value] = job
    return LastRunResponse(**response)

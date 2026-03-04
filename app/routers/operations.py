from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import JobStatus, JobType
from app.models.job import Job
from app.schemas.job import JobResponse, LastRunResponse
from app.services.job_runner import (
    run_export_job,
    run_fetch_job,
    run_rescore_job,
    run_score_job,
)

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


@router.post("/fetch", status_code=202, response_model=JobResponse)
async def start_fetch(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    await _check_no_running(session, [JobType.FETCH])
    job = await _create_job(session, JobType.FETCH)
    await session.commit()
    background_tasks.add_task(run_fetch_job, session, job.job_id)
    return job


@router.post("/score", status_code=202, response_model=JobResponse)
async def start_score(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    await _check_no_running(session, [JobType.SCORE, JobType.RESCORE])
    job = await _create_job(session, JobType.SCORE)
    await session.commit()
    background_tasks.add_task(run_score_job, session, job.job_id)
    return job


@router.post("/rescore", status_code=202, response_model=JobResponse)
async def start_rescore(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    await _check_no_running(session, [JobType.SCORE, JobType.RESCORE])
    job = await _create_job(session, JobType.RESCORE)
    await session.commit()
    background_tasks.add_task(run_rescore_job, session, job.job_id)
    return job


@router.post("/export", status_code=202, response_model=JobResponse)
async def start_export(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = await _create_job(session, JobType.EXPORT)
    await session.commit()
    background_tasks.add_task(run_export_job, session, job.job_id)
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

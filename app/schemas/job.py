from datetime import datetime
from typing import Optional

from app.schemas.base import AppBase


class JobResponse(AppBase):
    job_id: int
    job_type: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[dict] = None
    error_message: Optional[str] = None
    triggered_by: str
    created_at: datetime


class JobSummaryResponse(AppBase):
    job_id: int
    job_type: str
    status: str
    created_at: datetime


class LastRunResponse(AppBase):
    FETCH: Optional[JobResponse] = None
    SCORE: Optional[JobResponse] = None
    RESCORE: Optional[JobResponse] = None
    EXPORT: Optional[JobResponse] = None

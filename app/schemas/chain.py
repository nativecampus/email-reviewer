from datetime import datetime
from typing import Optional

from app.schemas.base import AppBase


class EmailChainCreate(AppBase):
    normalized_subject: str | None = None
    participants: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    email_count: int | None = None
    outgoing_count: int | None = None
    incoming_count: int | None = None


class EmailChainUpdate(AppBase):
    normalized_subject: str | None = None
    participants: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    email_count: int | None = None
    outgoing_count: int | None = None
    incoming_count: int | None = None


class EmailChainResponse(EmailChainCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

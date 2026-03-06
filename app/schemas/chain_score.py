from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.schemas.base import AppBase

CHAIN_SCORE_FIELDS = [
    "progression",
    "responsiveness",
    "persistence",
    "conversation_quality",
]


def _validate_chain_score_range(v: int) -> int:
    if not (1 <= v <= 10):
        raise ValueError("Score must be between 1 and 10")
    return v


class ChainScoringResult(BaseModel):
    progression: int
    responsiveness: int
    persistence: int
    conversation_quality: int
    notes: str

    @field_validator(*CHAIN_SCORE_FIELDS)
    @classmethod
    def score_in_range(cls, v: int) -> int:
        return _validate_chain_score_range(v)


class ChainScoreCreate(AppBase):
    chain_id: int
    progression: int
    responsiveness: int
    persistence: int
    conversation_quality: int
    avg_response_hours: float | None = None
    notes: str | None = None

    @field_validator(*CHAIN_SCORE_FIELDS)
    @classmethod
    def score_in_range(cls, v: int) -> int:
        return _validate_chain_score_range(v)


class ChainScoreUpdate(AppBase):
    progression: int | None = None
    responsiveness: int | None = None
    persistence: int | None = None
    conversation_quality: int | None = None
    avg_response_hours: float | None = None
    notes: str | None = None


class ChainScoreResponse(AppBase):
    id: int
    chain_id: int
    progression: int | None = None
    responsiveness: int | None = None
    persistence: int | None = None
    conversation_quality: int | None = None
    avg_response_hours: float | None = None
    notes: str | None = None
    score_error: bool = False
    scored_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

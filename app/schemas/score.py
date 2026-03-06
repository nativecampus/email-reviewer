from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.schemas.base import AppBase

SCORE_FIELDS = [
    "personalisation",
    "clarity",
    "value_proposition",
    "cta",
]


def _validate_score_range(v: int) -> int:
    if not (1 <= v <= 10):
        raise ValueError("Score must be between 1 and 10")
    return v


class ScoringResult(BaseModel):
    personalisation: int
    clarity: int
    value_proposition: int
    cta: int
    notes: str

    @field_validator(*SCORE_FIELDS)
    @classmethod
    def score_in_range(cls, v: int) -> int:
        return _validate_score_range(v)


class ScoreCreate(AppBase):
    email_id: int
    personalisation: int
    clarity: int
    value_proposition: int
    cta: int
    overall: int
    notes: str

    @field_validator(*SCORE_FIELDS)
    @classmethod
    def score_in_range(cls, v: int) -> int:
        return _validate_score_range(v)


class ScoreUpdate(AppBase):
    personalisation: Optional[int] = None
    clarity: Optional[int] = None
    value_proposition: Optional[int] = None
    cta: Optional[int] = None
    overall: Optional[int] = None
    notes: Optional[str] = None


class ScoreResponse(AppBase):
    id: int
    email_id: int
    personalisation: Optional[int] = None
    clarity: Optional[int] = None
    value_proposition: Optional[int] = None
    cta: Optional[int] = None
    overall: Optional[int] = None
    notes: Optional[str] = None
    score_error: bool = False
    scored_at: Optional[datetime] = None

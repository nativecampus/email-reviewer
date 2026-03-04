from datetime import date

from pydantic import field_validator

from app.schemas.base import AppBase


class SettingsResponse(AppBase):
    id: int
    global_start_date: date
    company_domains: str
    scoring_batch_size: int
    auto_score_after_fetch: bool


class SettingsUpdate(AppBase):
    global_start_date: date | None = None
    company_domains: str | None = None
    scoring_batch_size: int | None = None
    auto_score_after_fetch: bool | None = None

    @field_validator("global_start_date")
    @classmethod
    def start_date_not_in_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("global_start_date cannot be in the future")
        return v

    @field_validator("company_domains")
    @classmethod
    def domains_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("company_domains cannot be empty")
        return v

    @field_validator("scoring_batch_size")
    @classmethod
    def batch_size_positive(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("scoring_batch_size must be >= 1")
        return v

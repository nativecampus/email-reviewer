from typing import Optional

from app.schemas.base import AppBase


class RepCreate(AppBase):
    email: str
    display_name: str


class RepUpdate(AppBase):
    display_name: Optional[str] = None


class RepResponse(AppBase):
    email: str
    display_name: str


class RepTeamRow(AppBase):
    email: str
    display_name: str
    avg_personalisation: Optional[float] = None
    avg_clarity: Optional[float] = None
    avg_value_proposition: Optional[float] = None
    avg_cta: Optional[float] = None
    avg_overall: Optional[float] = None

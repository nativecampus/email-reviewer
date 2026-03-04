from datetime import date
from typing import Optional

from sqlalchemy import CheckConstraint, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base


class Settings(AuditMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row_settings"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    global_start_date: Mapped[date] = mapped_column(
        Date, default=date(2025, 9, 1)
    )
    company_domains: Mapped[str] = mapped_column(
        String, default="nativecampusadvertising.com,native.fm"
    )
    scoring_batch_size: Mapped[int] = mapped_column(Integer, default=5)
    auto_score_after_fetch: Mapped[bool] = mapped_column(default=True)

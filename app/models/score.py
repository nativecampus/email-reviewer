from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditMixin, Base


class Score(AuditMixin, Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    personalisation: Mapped[Optional[int]] = mapped_column(default=None)
    clarity: Mapped[Optional[int]] = mapped_column(default=None)
    value_proposition: Mapped[Optional[int]] = mapped_column(default=None)
    cta: Mapped[Optional[int]] = mapped_column(default=None)
    overall: Mapped[Optional[int]] = mapped_column(default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    score_error: Mapped[bool] = mapped_column(default=False)
    scored_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    email: Mapped["Email"] = relationship("Email", back_populates="score")

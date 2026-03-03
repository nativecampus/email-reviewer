from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditMixin, Base


class Email(AuditMixin, Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[Optional[datetime]] = mapped_column(default=None)
    from_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    from_email: Mapped[str] = mapped_column(String, nullable=False)
    to_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    to_email: Mapped[Optional[str]] = mapped_column(String, default=None)
    subject: Mapped[Optional[str]] = mapped_column(String, default=None)
    body_text: Mapped[Optional[str]] = mapped_column(Text, default=None)
    direction: Mapped[Optional[str]] = mapped_column(String, default=None)
    hubspot_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    score: Mapped[Optional["Score"]] = relationship(
        "Score",
        back_populates="email",
        uselist=False,
        cascade="all, delete-orphan",
    )

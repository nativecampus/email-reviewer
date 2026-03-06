from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.models.chain_score import ChainScore
    from app.models.email import Email


class EmailChain(AuditMixin, Base):
    __tablename__ = "email_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_subject: Mapped[Optional[str]] = mapped_column(String, default=None)
    participants: Mapped[Optional[str]] = mapped_column(String, default=None)
    started_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    email_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    outgoing_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    incoming_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)

    emails: Mapped[list["Email"]] = relationship(
        "Email",
        back_populates="chain",
    )
    chain_score: Mapped[Optional["ChainScore"]] = relationship(
        "ChainScore",
        back_populates="chain",
        uselist=False,
        cascade="all, delete-orphan",
    )

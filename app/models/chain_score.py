from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.models.chain import EmailChain


class ChainScore(AuditMixin, Base):
    __tablename__ = "chain_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("email_chains.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    progression: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    responsiveness: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    persistence: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    conversation_quality: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    avg_response_hours: Mapped[Optional[float]] = mapped_column(Float, default=None)
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)
    score_error: Mapped[bool] = mapped_column(default=False)
    scored_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    chain: Mapped["EmailChain"] = relationship(
        "EmailChain", back_populates="chain_score"
    )

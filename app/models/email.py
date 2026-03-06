from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AuditMixin, Base

if TYPE_CHECKING:
    from app.models.chain import EmailChain


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

    chain_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("email_chains.id"), default=None
    )
    position_in_chain: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    open_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    click_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    reply_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    message_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    in_reply_to: Mapped[Optional[str]] = mapped_column(String, default=None)
    thread_id: Mapped[Optional[str]] = mapped_column(String, default=None)

    score: Mapped[Optional["Score"]] = relationship(
        "Score",
        back_populates="email",
        uselist=False,
        cascade="all, delete-orphan",
    )
    chain: Mapped[Optional["EmailChain"]] = relationship(
        "EmailChain", back_populates="emails",
    )

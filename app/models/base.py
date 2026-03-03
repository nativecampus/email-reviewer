import os
from datetime import datetime, timezone

from sqlalchemy import String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _get_current_user() -> str:
    auth_enabled = os.getenv("AUTH_ENABLED", "FALSE").upper() == "TRUE"
    if not auth_enabled:
        return os.getenv("CURRENT_USER", "system")
    return "system"


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[str] = mapped_column(String, default="")
    updated_by: Mapped[str] = mapped_column(String, default="")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "__tablename__"):
            event.listen(cls, "before_insert", _before_insert)
            event.listen(cls, "before_update", _before_update)


def _before_insert(mapper, connection, target):
    user = _get_current_user()
    target.created_by = user
    target.updated_by = user
    target.created_at = datetime.now(timezone.utc)
    target.updated_at = datetime.now(timezone.utc)


def _before_update(mapper, connection, target):
    user = _get_current_user()
    target.updated_by = user
    target.updated_at = datetime.now(timezone.utc)

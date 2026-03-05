import math
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Email, Rep, Score


def _paginate_result(items, total: int, page: int, per_page: int | None):
    if per_page:
        pages = math.ceil(total / per_page)
    else:
        pages = 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


async def get_team(
    session: AsyncSession, *, page: int = 1, per_page: int | None = 20
):
    """JOIN emails/scores/reps, GROUP BY rep, compute AVGs, sort by overall desc."""
    base = (
        select(
            Rep.email,
            Rep.display_name,
            func.avg(Score.personalisation).label("avg_personalisation"),
            func.avg(Score.clarity).label("avg_clarity"),
            func.avg(Score.value_proposition).label("avg_value_proposition"),
            func.avg(Score.cta).label("avg_cta"),
            func.avg(Score.overall).label("avg_overall"),
        )
        .join(Email, Email.from_email == Rep.email)
        .join(Score, Score.email_id == Email.id)
        .group_by(Rep.email, Rep.display_name)
        .order_by(func.avg(Score.overall).desc())
    )

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    if per_page:
        base = base.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(base)
    return _paginate_result(result.all(), total, page, per_page)


async def get_rep_emails(
    session: AsyncSession,
    rep_email: str,
    *,
    page: int = 1,
    per_page: int | None = 20,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
):
    """Scored emails for one rep, ordered by date desc.

    Optional filters:
    - search: ILIKE match on subject or body_text
    - date_from / date_to: inclusive range on email timestamp
    - score_min / score_max: inclusive range on overall score
    """
    filters = [Email.from_email == rep_email]

    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Email.subject.ilike(pattern),
                Email.body_text.ilike(pattern),
            )
        )
    if date_from:
        filters.append(Email.timestamp >= date_from)
    if date_to:
        filters.append(Email.timestamp <= date_to)
    if score_min is not None:
        filters.append(Score.overall >= score_min)
    if score_max is not None:
        filters.append(Score.overall <= score_max)

    count_stmt = (
        select(func.count(Email.id))
        .join(Score, Score.email_id == Email.id)
        .where(*filters)
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Email)
        .join(Score, Score.email_id == Email.id)
        .where(*filters)
        .options(joinedload(Email.score))
        .order_by(Email.timestamp.desc())
    )

    if per_page:
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(stmt)
    items = result.scalars().unique().all()
    return _paginate_result(list(items), total, page, per_page)


async def get_email_detail(session: AsyncSession, email_id: int):
    """Single email with its score."""
    stmt = (
        select(Email)
        .where(Email.id == email_id)
        .options(joinedload(Email.score))
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_stats(session: AsyncSession):
    """Summary counts and averages."""
    total_emails_stmt = select(func.count(Email.id))
    total_scored_stmt = select(func.count(Score.id))
    total_reps_stmt = select(func.count(Rep.email))
    avg_overall_stmt = select(func.avg(Score.overall))

    total_emails = (await session.execute(total_emails_stmt)).scalar() or 0
    total_scored = (await session.execute(total_scored_stmt)).scalar() or 0
    total_reps = (await session.execute(total_reps_stmt)).scalar() or 0
    avg_overall = (await session.execute(avg_overall_stmt)).scalar()

    return {
        "total_emails": total_emails,
        "total_scored": total_scored,
        "total_reps": total_reps,
        "avg_overall": round(avg_overall, 2) if avg_overall is not None else None,
    }

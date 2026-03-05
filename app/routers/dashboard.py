from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Rep
from app.services.rep import get_rep_emails, get_team
from app.templating import templates

router = APIRouter()


def score_class(value) -> str:
    """Return a CSS class based on score value."""
    if value is None:
        return ""
    if value >= 7:
        return "score-high"
    if value >= 4:
        return "score-mid"
    return "score-low"


@router.get("/", include_in_schema=False)
async def team(request: Request, session: AsyncSession = Depends(get_db)):
    rows = await get_team(session)
    return templates.TemplateResponse(
        request,
        "team.html",
        {"rows": rows, "score_class": score_class},
    )


@router.get("/reps/{rep_email}", include_in_schema=False)
async def rep_detail(rep_email: str, request: Request, session: AsyncSession = Depends(get_db)):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    emails = await get_rep_emails(session, rep_email)
    return templates.TemplateResponse(
        request,
        "rep_detail.html",
        {"rep": rep, "emails": emails, "score_class": score_class},
    )

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Rep
from app.services.export import export_rep_emails
from app.services.rep import get_rep_emails, get_team
from app.templating import templates

router = APIRouter()

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


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
async def team(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=0),
    session: AsyncSession = Depends(get_db),
):
    effective_per_page = per_page or None
    result = await get_team(session, page=page, per_page=effective_per_page)
    start = (page - 1) * per_page + 1 if per_page else 1
    end = start + len(result["items"]) - 1 if result["items"] else 0
    return templates.TemplateResponse(
        request,
        "team.html",
        {
            "rows": result["items"],
            "score_class": score_class,
            "page": result["page"],
            "per_page": per_page,
            "total": result["total"],
            "pages": result["pages"],
            "start": start,
            "end": end,
        },
    )


@router.get("/reps/{rep_email}", include_in_schema=False)
async def rep_detail(
    rep_email: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=0),
    search: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    score_min: int | None = Query(None, ge=1, le=10),
    score_max: int | None = Query(None, ge=1, le=10),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    effective_per_page = per_page or None
    email_result = await get_rep_emails(
        session,
        rep_email,
        page=page,
        per_page=effective_per_page,
        search=search,
        date_from=date_from,
        date_to=date_to,
        score_min=score_min,
        score_max=score_max,
    )
    start = (page - 1) * per_page + 1 if per_page else 1
    end = start + len(email_result["items"]) - 1 if email_result["items"] else 0
    return templates.TemplateResponse(
        request,
        "rep_detail.html",
        {
            "rep": rep,
            "emails": email_result["items"],
            "score_class": score_class,
            "page": email_result["page"],
            "per_page": per_page,
            "total": email_result["total"],
            "pages": email_result["pages"],
            "start": start,
            "end": end,
            "search": search or "",
            "date_from": str(date_from) if date_from else "",
            "date_to": str(date_to) if date_to else "",
            "score_min": score_min or "",
            "score_max": score_max or "",
        },
    )


@router.get("/reps/{rep_email}/export", include_in_schema=False)
async def rep_export(
    rep_email: str,
    export_all: bool = Query(False),
    search: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    score_min: int | None = Query(None, ge=1, le=10),
    score_max: int | None = Query(None, ge=1, le=10),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    buf = await export_rep_emails(
        session,
        rep_email,
        search=search,
        date_from=date_from,
        date_to=date_to,
        score_min=score_min,
        score_max=score_max,
        export_all=export_all,
    )
    filename = f"{rep.display_name.replace(' ', '_')}_emails.xlsx"
    return StreamingResponse(
        buf,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

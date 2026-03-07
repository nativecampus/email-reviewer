from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Rep
from app.services.chain import get_chain_detail, get_rep_chains
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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


@router.get("/chains/{chain_id}", include_in_schema=False)
async def chain_detail_page(
    chain_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    chain = await get_chain_detail(session, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return templates.TemplateResponse(
        request,
        "chain_detail.html",
        {
            "chain": chain,
            "score_class": score_class,
        },
    )


@router.get("/reps/{rep_email}", include_in_schema=False)
async def rep_detail(
    rep_email: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=0),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    score_min: str = Query(""),
    score_max: str = Query(""),
    session: AsyncSession = Depends(get_db),
):
    stmt = select(Rep).where(Rep.email == rep_email)
    result = await session.execute(stmt)
    rep = result.scalars().first()
    if not rep:
        raise HTTPException(status_code=404, detail="Rep not found")

    parsed_date_from = _parse_date(date_from)
    parsed_date_to = _parse_date(date_to)
    parsed_score_min = _parse_int(score_min)
    parsed_score_max = _parse_int(score_max)

    effective_per_page = per_page or None
    email_result = await get_rep_emails(
        session,
        rep_email,
        page=page,
        per_page=effective_per_page,
        search=search or None,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
        score_min=parsed_score_min,
        score_max=parsed_score_max,
    )

    rep_chains_result = await get_rep_chains(session, rep_email, page=1, per_page=100)

    start = (page - 1) * per_page + 1 if per_page else 1
    end = start + len(email_result["items"]) - 1 if email_result["items"] else 0
    return templates.TemplateResponse(
        request,
        "rep_detail.html",
        {
            "rep": rep,
            "emails": email_result["items"],
            "chains": rep_chains_result["items"],
            "score_class": score_class,
            "page": email_result["page"],
            "per_page": per_page,
            "total": email_result["total"],
            "pages": email_result["pages"],
            "start": start,
            "end": end,
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "score_min": parsed_score_min or "",
            "score_max": parsed_score_max or "",
        },
    )


@router.get("/reps/{rep_email}/export", include_in_schema=False)
async def rep_export(
    rep_email: str,
    export_all: bool = Query(False),
    search: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    score_min: str = Query(""),
    score_max: str = Query(""),
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
        search=search or None,
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        score_min=_parse_int(score_min),
        score_max=_parse_int(score_max),
        export_all=export_all,
    )
    filename = f"{rep.display_name.replace(' ', '_')}_emails.xlsx"
    return StreamingResponse(
        buf,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

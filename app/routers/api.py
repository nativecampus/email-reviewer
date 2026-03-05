from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.rep import RepTeamRow
from app.schemas.score import ScoreResponse
from app.schemas.stats import StatsResponse
from app.services.rep import get_email_detail, get_rep_emails, get_stats, get_team

router = APIRouter(prefix="/api")


@router.get("/reps", response_model=list[RepTeamRow])
async def list_reps(session: AsyncSession = Depends(get_db)):
    rows = await get_team(session)
    return [
        RepTeamRow(
            email=r.email,
            display_name=r.display_name,
            avg_personalisation=round(r.avg_personalisation, 2) if r.avg_personalisation else None,
            avg_clarity=round(r.avg_clarity, 2) if r.avg_clarity else None,
            avg_value_proposition=round(r.avg_value_proposition, 2) if r.avg_value_proposition else None,
            avg_cta=round(r.avg_cta, 2) if r.avg_cta else None,
            avg_overall=round(r.avg_overall, 2) if r.avg_overall else None,
        )
        for r in rows
    ]


@router.get("/reps/{rep_email}/emails")
async def list_rep_emails(rep_email: str, session: AsyncSession = Depends(get_db)):
    emails = await get_rep_emails(session, rep_email)
    return [
        {
            "id": e.id,
            "subject": e.subject,
            "from_email": e.from_email,
            "to_email": e.to_email,
            "timestamp": e.timestamp,
            "score": {
                "overall": e.score.overall,
                "personalisation": e.score.personalisation,
                "clarity": e.score.clarity,
                "value_proposition": e.score.value_proposition,
                "cta": e.score.cta,
                "notes": e.score.notes,
            } if e.score else None,
        }
        for e in emails
    ]


@router.get("/emails/{email_id}")
async def email_detail(email_id: int, session: AsyncSession = Depends(get_db)):
    email = await get_email_detail(session, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return {
        "id": email.id,
        "subject": email.subject,
        "from_email": email.from_email,
        "to_email": email.to_email,
        "body_text": email.body_text,
        "timestamp": email.timestamp,
        "score": {
            "id": email.score.id,
            "overall": email.score.overall,
            "personalisation": email.score.personalisation,
            "clarity": email.score.clarity,
            "value_proposition": email.score.value_proposition,
            "cta": email.score.cta,
            "notes": email.score.notes,
            "score_error": email.score.score_error,
            "scored_at": email.score.scored_at,
        } if email.score else None,
    }


@router.get("/stats", response_model=StatsResponse)
async def stats(session: AsyncSession = Depends(get_db)):
    return await get_stats(session)

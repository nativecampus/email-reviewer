from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services.settings import get_settings, update_settings
from app.templating import templates

router = APIRouter()


@router.get("/api/settings", response_model=SettingsResponse)
async def read_settings(session: AsyncSession = Depends(get_db)):
    return await get_settings(session)


@router.patch("/api/settings", response_model=SettingsResponse)
async def patch_settings(
    updates: SettingsUpdate, session: AsyncSession = Depends(get_db)
):
    return await update_settings(session, updates)


@router.get("/settings", include_in_schema=False)
async def settings_page(request: Request, session: AsyncSession = Depends(get_db)):
    settings = await get_settings(session)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings},
    )

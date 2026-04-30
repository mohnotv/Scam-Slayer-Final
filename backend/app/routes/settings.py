from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AppSetting
from backend.app.db.session import get_db
from backend.app.config import settings as env_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class LlmProviderOut(BaseModel):
    provider: str


class LlmProviderIn(BaseModel):
    provider: str


@router.get("/llm", response_model=LlmProviderOut)
async def get_llm(db: AsyncSession = Depends(get_db)) -> LlmProviderOut:
    q = await db.execute(select(AppSetting).where(AppSetting.key == "active_llm_provider"))
    s = q.scalar_one_or_none()
    provider = (s.value.strip() if s and s.value.strip() else env_settings.llm_provider).lower()
    return LlmProviderOut(provider=provider)


@router.put("/llm", response_model=LlmProviderOut)
async def set_llm(body: LlmProviderIn, db: AsyncSession = Depends(get_db)) -> LlmProviderOut:
    provider = body.provider.strip().lower()
    if provider not in {"gemini", "anthropic"}:
        raise HTTPException(status_code=400, detail="provider must be gemini or anthropic")

    q = await db.execute(select(AppSetting).where(AppSetting.key == "active_llm_provider"))
    s = q.scalar_one_or_none()
    if s is None:
        s = AppSetting(key="active_llm_provider", value=provider)
    else:
        s.value = provider
    db.add(s)
    await db.commit()
    return LlmProviderOut(provider=provider)


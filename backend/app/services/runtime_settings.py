from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import AppSetting


async def get_active_llm_provider(db: AsyncSession) -> str:
    """
    Return the runtime-selected LLM provider.

    Falls back to env-configured settings.llm_provider.
    """
    q = await db.execute(select(AppSetting).where(AppSetting.key == "active_llm_provider"))
    s = q.scalar_one_or_none()
    if s and s.value.strip():
        return s.value.strip().lower()
    return settings.llm_provider.strip().lower()


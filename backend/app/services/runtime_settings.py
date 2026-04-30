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
    if s and (s.value or "").strip():
        v = s.value.strip().lower()
        if v in ("anthropic", "gemini"):
            return v
    env = (settings.llm_provider or "").strip().lower()
    return env if env in ("anthropic", "gemini") else "gemini"


async def get_dialogue_preferences(db: AsyncSession) -> dict[str, str]:
    """
    Return persisted dialogue behavior preferences.

    Keys:
      - dialogue_goal: "engage" | "clarify"
      - humor_level: "high" | "medium" | "low" | "off"
    """
    defaults = {"dialogue_goal": "engage", "humor_level": "high"}
    out: dict[str, str] = dict(defaults)
    q = await db.execute(
        select(AppSetting).where(AppSetting.key.in_(list(defaults.keys())))
    )
    rows = q.scalars().all()
    for s in rows:
        if not s or not (s.value or "").strip():
            continue
        v = s.value.strip().lower()
        if s.key == "dialogue_goal" and v in {"engage", "clarify"}:
            out["dialogue_goal"] = v
        if s.key == "humor_level" and v in {"high", "medium", "low", "off"}:
            out["humor_level"] = v
    return out


async def set_dialogue_preferences(db: AsyncSession, *, dialogue_goal: str, humor_level: str) -> dict[str, str]:
    goal = (dialogue_goal or "").strip().lower()
    humor = (humor_level or "").strip().lower()
    if goal not in {"engage", "clarify"}:
        raise ValueError("dialogue_goal must be 'engage' or 'clarify'")
    if humor not in {"high", "medium", "low", "off"}:
        raise ValueError("humor_level must be one of: high, medium, low, off")

    for k, v in {"dialogue_goal": goal, "humor_level": humor}.items():
        q = await db.execute(select(AppSetting).where(AppSetting.key == k))
        s = q.scalar_one_or_none()
        if s is None:
            s = AppSetting(key=k, value=v)
        else:
            s.value = v
        db.add(s)
    await db.commit()
    return {"dialogue_goal": goal, "humor_level": humor}


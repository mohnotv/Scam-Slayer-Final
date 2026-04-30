"""
Voices API (ElevenLabs).

Lists available voices from the connected ElevenLabs account and allows locking
an "active" voice override for live calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import AppSetting, Persona
from backend.app.db.session import get_db

import httpx

router = APIRouter(prefix="/voices", tags=["voices"])


class VoiceOut(BaseModel):
    voice_id: str
    name: str


@router.get("", response_model=list[VoiceOut])
async def list_voices(db: AsyncSession = Depends(get_db)) -> list[VoiceOut]:
    api_key = settings.elevenlabs_api_key
    if not api_key or api_key == "placeholder":
        return []

    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": api_key, "accept": "application/json"}
    timeout = httpx.Timeout(connect=8.0, read=20.0, write=8.0, pool=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers=headers)

    # Helpful for debugging key/permission issues in dev.
    if r.status_code >= 400:
        from backend.app.routes.voice import logger as _voice_logger  # avoid creating another logger config

        _voice_logger.warning("ElevenLabs /v1/voices status=%s body=%s", r.status_code, r.text[:200])

    if r.status_code == 401:
        # Fallback: return the voices currently referenced by personas so the UI can still switch.
        # This keeps the app usable even if /v1/voices is blocked / keys lack permission.
        q = await db.execute(select(Persona).order_by(Persona.name))
        personas = q.scalars().all()
        seen: set[str] = set()
        out: list[VoiceOut] = []
        for p in personas:
            if p.elevenlabs_voice_id and p.elevenlabs_voice_id not in seen:
                seen.add(p.elevenlabs_voice_id)
                out.append(VoiceOut(voice_id=p.elevenlabs_voice_id, name=f"{p.name} (default)"))
        return out
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"ElevenLabs voices error {r.status_code}: {r.text[:200]}")

    data = r.json()
    voices = data.get("voices") or []
    out: list[VoiceOut] = []
    for v in voices:
        vid = v.get("voice_id")
        name = v.get("name")
        if isinstance(vid, str) and isinstance(name, str):
            out.append(VoiceOut(voice_id=vid, name=name))
    return sorted(out, key=lambda x: x.name.lower())


"""
Clips REST API

GET  /clips                   — list all clips (newest first)
GET  /clips/{id}              — single clip metadata
GET  /clips/{id}/download     — stream the .mp4 file
POST /clips/{call_id}/generate — trigger editor + social agents for a completed call
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.editor import EditorAgent
from backend.app.agents.highlights import HighlightData, HighlightMinerAgent, HighlightsResult
from backend.app.agents.social import SocialAgent
from backend.app.db.models import Call, Clip, Highlight
from backend.app.db.session import get_db

router = APIRouter(prefix="/clips", tags=["clips"])


class ClipOut(BaseModel):
    id: int
    call_id: int
    file_path: str
    duration_seconds: float
    caption: str
    hashtags: list[str]
    status: str

    model_config = {"from_attributes": True}


def _orm_to_out(c: Clip) -> ClipOut:
    return ClipOut(
        id=c.id,
        call_id=c.call_id,
        file_path=c.file_path,
        duration_seconds=c.duration_seconds,
        caption=c.caption,
        hashtags=json.loads(c.hashtags) if c.hashtags else [],
        status=c.status,
    )


def _highlights_from_orm(call_id: int, rows: list[Highlight]) -> HighlightsResult:
    """Convert fetched Highlight ORM rows to HighlightsResult for agent consumption."""
    return HighlightsResult(
        call_id=call_id,
        highlights=[
            HighlightData(
                db_id=h.id,
                start_ms=h.start_ms,
                end_ms=h.end_ms,
                reason=h.reason,
                score=h.score,
                transcript_snippet=h.transcript_snippet,
            )
            for h in rows
        ],
    )


@router.get("", response_model=list[ClipOut])
async def list_clips(db: AsyncSession = Depends(get_db)) -> list[ClipOut]:
    result = await db.execute(select(Clip).order_by(Clip.created_at.desc()))
    return [_orm_to_out(c) for c in result.scalars().all()]


@router.get("/{clip_id}", response_model=ClipOut)
async def get_clip(clip_id: int, db: AsyncSession = Depends(get_db)) -> ClipOut:
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return _orm_to_out(clip)


@router.get("/{clip_id}/download")
async def download_clip(clip_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    if not clip.file_path or not Path(clip.file_path).exists():
        raise HTTPException(status_code=404, detail="Clip file not yet rendered")
    return FileResponse(
        clip.file_path,
        media_type="video/mp4",
        filename=Path(clip.file_path).name,
    )


@router.post("/{call_id}/generate", response_model=ClipOut, status_code=202)
async def generate_clip(
    call_id: int,
    db: AsyncSession = Depends(get_db),
) -> ClipOut:
    """
    Run the Editor + Social agents for a completed call.

    If highlights haven't been mined yet, mines them first.
    Returns the Clip row immediately (status may be "stub" or "ready").
    """
    call_q = await db.execute(select(Call).where(Call.id == call_id))
    call = call_q.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Use existing highlights if already mined; otherwise mine now.
    existing_q = await db.execute(
        select(Highlight).where(Highlight.call_id == call_id).order_by(Highlight.score.desc())
    )
    existing = list(existing_q.scalars().all())

    if existing:
        highlights = _highlights_from_orm(call_id, existing)
    else:
        highlights = await HighlightMinerAgent(db).run(call_id)

    editor_result = await EditorAgent(db).run(call_id, highlights, audio_path=None)

    await SocialAgent(db).run(
        call_id=call_id,
        clip_db_id=editor_result.db_id,
        clip_duration_seconds=editor_result.duration_seconds,
        call_duration_seconds=call.duration_seconds,
        highlights=highlights,
    )

    clip_q = await db.execute(select(Clip).where(Clip.id == editor_result.db_id))
    clip = clip_q.scalar_one()
    return _orm_to_out(clip)

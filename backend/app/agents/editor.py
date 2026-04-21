"""
Editor Agent

Inputs:  Call, list of Highlight rows, path to raw call audio file
Outputs: Clip DB row with path to rendered .mp4 (vertical 9:16)
Side effects: writes clip file to disk; INSERTs Clip row; logs AgentEvent

MVP status: STUB — ffmpeg plumbing defined but clip assembly not yet complete.
            Returns a Clip row with status="pending" and no file on disk.
Next step: wire whisper-timestamped → SRT → ffmpeg burn-in; add intro/outro cards.
"""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Clip, Highlight


CLIPS_DIR = Path("clips")


async def assemble_clip(
    call_id: int,
    highlights: list[Highlight],
    audio_path: str | None,
    db: AsyncSession,
) -> Clip:
    """
    Stitch highlight windows into a vertical short-form video clip.

    Args:
        call_id:    DB id of the ended Call.
        highlights: Ordered list of Highlight instances to include.
        audio_path: Path to the raw mulaw/wav call recording (None if not yet available).
        db:         Async DB session.

    Returns:
        A Clip ORM instance (status="pending" until ffmpeg finishes).
    """
    CLIPS_DIR.mkdir(exist_ok=True)
    output_path = str(CLIPS_DIR / f"call_{call_id}_highlight.mp4")

    clip = Clip(
        call_id=call_id,
        file_path=output_path,
        duration_seconds=sum((h.end_ms - h.start_ms) for h in highlights) / 1000,
        status="pending",
    )
    db.add(clip)
    await db.flush()  # get clip.id before commit

    event = AgentEvent(
        call_id=call_id,
        agent="editor",
        event_type="clip_assembly_queued",
        payload={
            "clip_id": clip.id,
            "output_path": output_path,
            "highlight_count": len(highlights),
            "audio_path": audio_path,
        },
    )
    db.add(event)
    await db.commit()

    # TODO: dispatch to arq background job for actual ffmpeg work
    # await _run_ffmpeg(highlights, audio_path, output_path)

    return clip


async def _run_ffmpeg(
    highlights: list[Highlight],
    audio_path: str,
    output_path: str,
) -> None:
    """
    STUB: build ffmpeg command to:
    1. Extract highlight windows from audio
    2. Generate waveform / static background (9:16 1080x1920)
    3. Burn in SRT captions via whisper-timestamped
    4. Add intro/outro title cards
    5. Concatenate and export
    """
    raise NotImplementedError("ffmpeg clip assembly not yet implemented")

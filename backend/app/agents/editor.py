"""
Editor Agent

Inputs:
    call_id    — DB id of the ended Call
    highlights — HighlightsResult from the Highlight Miner Agent
    audio_path — optional path to the raw mulaw/wav call recording (None during mock phase)

Outputs:
    EditorResult — db_id, file_path, duration_seconds, status

Side effects:
    Writes a placeholder .mp4 file to disk (clips/ directory).
    INSERTs a Clip row.
    Writes one AgentEvent row.

File strategy (in priority order):
    1. If ffmpeg is in PATH, generate a real 1-second black vertical clip (1080×1920).
    2. Otherwise write a zero-byte stub file with a .mp4 extension.
    The file always exists on disk after run() returns so downstream tests can Path.exists() it.

Next step: wire whisper-timestamped → SRT → ffmpeg burn-in for real highlight stitching;
           add branded intro/outro cards; use audio_path when Twilio recording is available.
"""

import asyncio
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.highlights import HighlightsResult
from backend.app.db.models import AgentEvent, Clip

logger = logging.getLogger(__name__)

_CLIPS_DIR = Path("clips")


class EditorResult(BaseModel):
    """Typed output of the Editor Agent."""

    db_id: int
    file_path: str
    duration_seconds: float
    status: str  # "ready" | "stub" | "pending"


class EditorAgent:
    """
    Assembles highlight windows into a short-form vertical video clip.

    Instantiate per-request and call ``await agent.run(...)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        call_id: int,
        highlights: HighlightsResult,
        audio_path: str | None = None,
    ) -> EditorResult:
        """
        Write a placeholder .mp4 and persist a Clip row.

        Args:
            call_id:    DB id of the ended Call.
            highlights: Output from HighlightMinerAgent.run().
            audio_path: Path to call recording; None during mock phase.

        Returns:
            EditorResult with the clip's db_id and file path.
        """
        _CLIPS_DIR.mkdir(exist_ok=True)
        output_path = _CLIPS_DIR / f"call_{call_id}_highlight.mp4"
        duration = sum(
            (h.end_ms - h.start_ms) for h in highlights.highlights
        ) / 1000.0

        status = await self._write_placeholder(output_path)
        logger.info("EditorAgent: wrote %s (status=%s)", output_path, status)

        clip = Clip(
            call_id=call_id,
            file_path=str(output_path),
            duration_seconds=duration,
            status=status,
        )
        self._db.add(clip)
        await self._db.flush()  # get clip.id

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="editor",
            event_type="clip_written",
            payload={
                "clip_id": clip.id,
                "output_path": str(output_path),
                "duration_seconds": duration,
                "status": status,
                "highlight_count": len(highlights.highlights),
                "audio_path": audio_path,
                "ffmpeg_available": shutil.which("ffmpeg") is not None,
            },
        ))
        await self._db.commit()

        return EditorResult(
            db_id=clip.id,
            file_path=str(output_path),
            duration_seconds=duration,
            status=status,
        )

    @staticmethod
    async def _write_placeholder(path: Path) -> str:
        """
        Write a minimal valid video file.

        Tries ffmpeg first (1-second black 1080×1920 clip).
        Falls back to a zero-byte stub if ffmpeg is not installed.
        Returns "ready" | "stub".
        """
        if shutil.which("ffmpeg"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    "-f", "lavfi",
                    "-i", "color=c=black:s=1080x1920:r=1",
                    "-t", "1",
                    "-pix_fmt", "yuv420p",
                    str(path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                if proc.returncode == 0 and path.exists():
                    return "ready"
            except OSError:
                pass

        # Fallback: zero-byte stub so Path.exists() passes in tests
        path.write_bytes(b"")
        return "stub"

    @staticmethod
    async def _assemble_real(
        highlights: HighlightsResult,
        audio_path: str,
        output_path: Path,
    ) -> None:
        """
        NOT YET IMPLEMENTED.

        Future implementation will:
        1. Extract highlight windows from audio_path using ffmpeg trim filters
        2. Run whisper-timestamped on each window → per-word SRT
        3. Burn captions into a black 1080×1920 background via ffmpeg subtitles filter
        4. Add branded intro card (ScamSlayer logo + scam type label)
        5. Concatenate windows with ffmpeg concat demuxer
        6. Export final MP4 with AAC audio
        """
        raise NotImplementedError("Real ffmpeg assembly not yet implemented")

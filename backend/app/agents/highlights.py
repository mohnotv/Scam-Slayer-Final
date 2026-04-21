"""
Highlight Miner Agent

Inputs:
    call_id — DB id of the ended Call (segments are fetched from DB internally)

Outputs:
    HighlightsResult — list of HighlightData items with timestamps, reasons, scores

Side effects:
    INSERTs Highlight rows into the DB.
    Writes one AgentEvent row.

Mock status: returns 3 hardcoded highlight windows with placeholder reasons.
             Snippets are pulled from the actual transcript segments when present;
             otherwise falls back to fixture text.
Next step: run sentiment analysis + volume envelope on the call audio to detect
           genuine frustration spikes; score each highlight by predicted virality
           using the features from analysis/03_virality_features.ipynb.
"""

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Highlight, TranscriptSegment


class HighlightData(BaseModel):
    """A single highlight moment within a call."""

    db_id: int
    start_ms: int
    end_ms: int
    reason: str   # human-readable label for the dashboard
    score: float = Field(ge=0.0, le=1.0)  # predicted virality 0–1
    transcript_snippet: str


class HighlightsResult(BaseModel):
    """Typed output of the Highlight Miner Agent."""

    call_id: int
    highlights: list[HighlightData]


# ── Mock highlight templates ──────────────────────────────────────────────────

_MOCK_TEMPLATES: list[dict] = [
    {
        "start_ms": 12_000,
        "end_ms": 27_000,
        "reason": "frustration spike detected",
        "score": 0.87,
        "fallback_snippet": "Hello, is this the IRS? You owe back taxes!",
    },
    {
        "start_ms": 54_000,
        "end_ms": 71_000,
        "reason": "comedic stall",
        "score": 0.91,
        "fallback_snippet": "Now hold on, Mr. Whiskers is sitting on my telephone…",
    },
    {
        "start_ms": 94_000,
        "end_ms": 112_000,
        "reason": "peak confusion moment",
        "score": 0.94,
        "fallback_snippet": "Should I call my grandson Bobby? He knows about computers.",
    },
]


class HighlightMinerAgent:
    """
    Mines a completed call's transcript for highlight-worthy moments.

    Instantiate per-request and call ``await agent.run(call_id)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(self, call_id: int) -> HighlightsResult:
        """
        Identify and persist highlights for a completed call.

        Fetches final TranscriptSegment rows, runs mock detection,
        INSERTs Highlight rows, and returns HighlightsResult.
        """
        segments = await self._fetch_final_segments(call_id)
        orm_highlights = self._mine_mock(call_id, segments)

        for h in orm_highlights:
            self._db.add(h)
        await self._db.flush()  # populate h.id before commit

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="highlights",
            event_type="highlights_mined",
            payload={
                "highlight_count": len(orm_highlights),
                "mocked": True,
                "segment_count": len(segments),
            },
        ))
        await self._db.commit()

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
                for h in orm_highlights
            ],
        )

    async def _fetch_final_segments(self, call_id: int) -> list[TranscriptSegment]:
        result = await self._db.execute(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.call_id == call_id,
                TranscriptSegment.is_final == True,  # noqa: E712
            )
            .order_by(TranscriptSegment.timestamp_ms)
        )
        return list(result.scalars().all())

    @staticmethod
    def _mine_mock(call_id: int, segments: list[TranscriptSegment]) -> list[Highlight]:
        """
        MOCK: return 3 fixture highlights, pulling real transcript snippets where available.
        Replace this with real audio/NLP analysis when ready.
        """
        highlights: list[Highlight] = []
        for i, tpl in enumerate(_MOCK_TEMPLATES):
            snippet = segments[i % len(segments)].text if segments else tpl["fallback_snippet"]
            highlights.append(Highlight(
                call_id=call_id,
                start_ms=tpl["start_ms"],
                end_ms=tpl["end_ms"],
                reason=tpl["reason"],
                score=tpl["score"],
                transcript_snippet=snippet,
            ))
        return highlights

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
from backend.app.services.llm_client import generate_text
from backend.app.services.runtime_settings import get_active_llm_provider


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

_MOCK_TEMPLATES: list[dict[str, object]] = [
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
        try:
            orm_highlights = await self._mine_llm(call_id, segments)
            mocked = False
        except Exception:
            orm_highlights = self._mine_mock(call_id, segments)
            mocked = True

        for h in orm_highlights:
            self._db.add(h)
        await self._db.flush()  # populate h.id before commit

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="highlights",
            event_type="highlights_mined",
            payload={
                "highlight_count": len(orm_highlights),
                "mocked": mocked,
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

    async def _mine_llm(self, call_id: int, segments: list[TranscriptSegment]) -> list[Highlight]:
        transcript = "\n".join([f"{s.speaker}: {s.text}" for s in segments])[:8000]
        system = (
            "You are a highlight miner for scam-bait call transcripts.\n"
            "Return JSON only: {highlights:[{start_ms,end_ms,reason,score,transcript_snippet}]}.\n"
            "Pick exactly 3 highlights. score is 0-1."
        )
        user = f"Transcript:\n{transcript}\n\nReturn 3 highlight moments."
        provider = await get_active_llm_provider(self._db)
        text = await generate_text(
            provider=provider,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=400,
        )
        import json

        data = json.loads(text)
        out: list[Highlight] = []
        for h in (data.get("highlights") or [])[:3]:
            out.append(
                Highlight(
                    call_id=call_id,
                    start_ms=int(h.get("start_ms", 0)),
                    end_ms=int(h.get("end_ms", 0)),
                    reason=str(h.get("reason", "highlight")),
                    score=float(h.get("score", 0.5)),
                    transcript_snippet=str(h.get("transcript_snippet", ""))[:240],
                )
            )
        if len(out) != 3:
            raise ValueError("LLM highlights did not return 3 items")
        return out

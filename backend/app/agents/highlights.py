"""
Highlight Miner Agent

Inputs:  completed Call DB row + its TranscriptSegment rows
Outputs: list of Highlight DB rows (timestamp-tagged clips)
Side effects: INSERTs Highlight rows; logs AgentEvent

MVP status: MOCK — returns two hardcoded highlight windows from the transcript.
Next step: run sentiment analysis + volume envelope on the audio to detect
           frustration spikes; score highlights by predicted virality.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Highlight, TranscriptSegment


async def mine_highlights(
    call_id: int,
    db: AsyncSession,
) -> list[Highlight]:
    """
    Scan the call transcript and audio for highlight-worthy moments.

    Args:
        call_id: DB id of the ended Call.
        db:      Async DB session.

    Returns:
        List of persisted Highlight ORM instances.
    """
    result = await db.execute(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.call_id == call_id,
            TranscriptSegment.is_final == True,  # noqa: E712
        )
        .order_by(TranscriptSegment.timestamp_ms)
    )
    segments = result.scalars().all()

    highlights = _mine_mock(call_id, list(segments))

    for h in highlights:
        db.add(h)

    event = AgentEvent(
        call_id=call_id,
        agent="highlights",
        event_type="highlights_mined",
        payload={"highlight_count": len(highlights)},
    )
    db.add(event)
    await db.commit()

    return highlights


def _mine_mock(call_id: int, transcripts: list[TranscriptSegment]) -> list[Highlight]:
    """
    MOCK: return two fixture highlights regardless of transcript content.
    In real implementation: run frustration spike detection here.
    """
    snippet_a = transcripts[0].text if transcripts else "Hello, is this the IRS?"
    snippet_b = transcripts[-1].text if len(transcripts) > 1 else "I'll go get my gift cards."

    return [
        Highlight(
            call_id=call_id,
            start_ms=12000,
            end_ms=27000,
            reason="Scammer frustration spike — repeated demands",
            score=0.87,
            transcript_snippet=snippet_a,
        ),
        Highlight(
            call_id=call_id,
            start_ms=94000,
            end_ms=112000,
            reason="Betty mentions Mr. Whiskers mid-SSN-read",
            score=0.94,
            transcript_snippet=snippet_b,
        ),
    ]

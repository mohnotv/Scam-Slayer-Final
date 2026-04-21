"""
Highlight Miner Agent tests.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.highlights import HighlightMinerAgent, HighlightsResult, HighlightData
from backend.app.db.models import AgentEvent, Call, Highlight, TranscriptSegment


@pytest.mark.asyncio
async def test_run_returns_highlights_result(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    assert isinstance(result, HighlightsResult)


@pytest.mark.asyncio
async def test_returns_three_mock_highlights(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    assert len(result.highlights) == 3


@pytest.mark.asyncio
async def test_call_id_matches(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    assert result.call_id == call.id


@pytest.mark.asyncio
async def test_highlight_items_are_typed(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    for h in result.highlights:
        assert isinstance(h, HighlightData)


@pytest.mark.asyncio
async def test_start_before_end(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    for h in result.highlights:
        assert h.start_ms < h.end_ms


@pytest.mark.asyncio
async def test_scores_in_range(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    for h in result.highlights:
        assert 0.0 <= h.score <= 1.0


@pytest.mark.asyncio
async def test_reasons_are_nonempty(db: AsyncSession, call: Call) -> None:
    result = await HighlightMinerAgent(db).run(call.id)
    for h in result.highlights:
        assert len(h.reason) > 0


@pytest.mark.asyncio
async def test_reasons_use_expected_labels(db: AsyncSession, call: Call) -> None:
    """Reasons should come from the defined mock templates."""
    expected_reasons = {"frustration spike detected", "comedic stall", "peak confusion moment"}
    result = await HighlightMinerAgent(db).run(call.id)
    actual = {h.reason for h in result.highlights}
    assert actual == expected_reasons


@pytest.mark.asyncio
async def test_persists_highlight_rows(db: AsyncSession, call: Call) -> None:
    await HighlightMinerAgent(db).run(call.id)

    q = await db.execute(select(Highlight).where(Highlight.call_id == call.id))
    rows = q.scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_db_ids_match_orm(db: AsyncSession, call: Call) -> None:
    """HighlightData.db_id should correspond to the actual Highlight.id in DB."""
    result = await HighlightMinerAgent(db).run(call.id)

    q = await db.execute(select(Highlight).where(Highlight.call_id == call.id))
    orm_ids = {h.id for h in q.scalars().all()}
    result_ids = {h.db_id for h in result.highlights}

    assert result_ids == orm_ids


@pytest.mark.asyncio
async def test_persists_agent_event(db: AsyncSession, call: Call) -> None:
    await HighlightMinerAgent(db).run(call.id)

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "highlights",
        )
    )
    event = q.scalar_one()
    assert event.event_type == "highlights_mined"
    assert event.payload["highlight_count"] == 3
    assert event.payload["mocked"] is True


@pytest.mark.asyncio
async def test_uses_real_transcript_snippets(db: AsyncSession, call: Call) -> None:
    """When transcript segments exist, their text should appear in highlights."""
    db.add(TranscriptSegment(
        call_id=call.id,
        speaker="scammer",
        text="I will have you arrested today!",
        timestamp_ms=1000,
        is_final=True,
    ))
    await db.commit()

    result = await HighlightMinerAgent(db).run(call.id)
    snippets = [h.transcript_snippet for h in result.highlights]
    assert "I will have you arrested today!" in snippets


@pytest.mark.asyncio
async def test_falls_back_when_no_segments(db: AsyncSession, call: Call) -> None:
    """With no transcript segments, highlights should still be produced (fallback text)."""
    result = await HighlightMinerAgent(db).run(call.id)
    assert len(result.highlights) == 3
    for h in result.highlights:
        assert len(h.transcript_snippet) > 0

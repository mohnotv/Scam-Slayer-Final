"""
Social Agent tests.
"""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.highlights import HighlightData, HighlightsResult
from backend.app.agents.social import SocialAgent, SocialResult
from backend.app.db.models import AgentEvent, Call, Clip


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def clip(db: AsyncSession, call: Call) -> Clip:
    c = Clip(call_id=call.id, status="stub")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest.fixture
def mock_highlights(call: Call) -> HighlightsResult:
    return HighlightsResult(
        call_id=call.id,
        highlights=[
            HighlightData(
                db_id=1, start_ms=10_000, end_ms=25_000,
                reason="frustration spike detected", score=0.87,
                transcript_snippet="Pay up or face arrest!",
            ),
            HighlightData(
                db_id=2, start_ms=60_000, end_ms=75_000,
                reason="comedic stall", score=0.94,
                transcript_snippet="Mr. Whiskers, not now honey!",
            ),
        ],
    )


async def _run(
    db: AsyncSession,
    call: Call,
    clip: Clip,
    highlights: HighlightsResult,
    call_duration: int = 420,
) -> SocialResult:
    return await SocialAgent(db).run(
        call_id=call.id,
        clip_db_id=clip.id,
        clip_duration_seconds=30.0,
        call_duration_seconds=call_duration,
        highlights=highlights,
    )


# ── Return type ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_returns_social_result(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert isinstance(result, SocialResult)


# ── Caption ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_caption_is_nonempty(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert len(result.caption.strip()) > 0


@pytest.mark.asyncio
async def test_caption_contains_grandma_betty(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert "Betty" in result.caption or "Grandma" in result.caption


@pytest.mark.asyncio
async def test_caption_contains_best_snippet(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    """The highest-scoring highlight's snippet should appear in the caption."""
    result = await _run(db, call, clip, mock_highlights)
    # best highlight score=0.94 → snippet "Mr. Whiskers, not now honey!"
    assert "Mr. Whiskers" in result.caption


@pytest.mark.asyncio
async def test_caption_reflects_call_duration(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    """Duration in minutes should appear in the caption text."""
    result = await _run(db, call, clip, mock_highlights, call_duration=300)
    assert "5" in result.caption  # 300s = 5 minutes


@pytest.mark.asyncio
async def test_caption_handles_empty_highlights(
    db: AsyncSession, call: Call, clip: Clip
) -> None:
    empty = HighlightsResult(call_id=call.id, highlights=[])
    result = await _run(db, call, clip, empty)
    assert isinstance(result.caption, str)
    assert len(result.caption) > 0


# ── Hashtags ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hashtags_is_nonempty_list(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert isinstance(result.hashtags, list)
    assert len(result.hashtags) >= 5


@pytest.mark.asyncio
async def test_hashtags_all_start_with_hash(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    for tag in result.hashtags:
        assert tag.startswith("#"), f"Expected # prefix: {tag}"


@pytest.mark.asyncio
async def test_hashtags_include_scambaiting(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert "#scambaiting" in result.hashtags


# ── Post time ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggested_post_time_nonempty(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)
    assert isinstance(result.suggested_post_time, str)
    assert len(result.suggested_post_time) > 0


# ── DB persistence ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_updates_clip_caption(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)

    q = await db.execute(select(Clip).where(Clip.id == clip.id))
    updated = q.scalar_one()
    assert updated.caption == result.caption


@pytest.mark.asyncio
async def test_updates_clip_hashtags(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)

    q = await db.execute(select(Clip).where(Clip.id == clip.id))
    updated = q.scalar_one()
    assert json.loads(updated.hashtags) == result.hashtags


@pytest.mark.asyncio
async def test_persists_agent_event(
    db: AsyncSession, call: Call, clip: Clip, mock_highlights: HighlightsResult
) -> None:
    result = await _run(db, call, clip, mock_highlights)

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "social",
        )
    )
    event = q.scalar_one()
    assert event.event_type == "social_package_generated"
    assert event.payload["clip_id"] == clip.id
    assert event.payload["hashtag_count"] == len(result.hashtags)
    assert event.payload["mocked"] is True

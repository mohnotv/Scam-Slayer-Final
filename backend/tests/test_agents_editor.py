"""
Editor Agent tests.

The agent writes a file to disk.  Tests clean up after themselves.
"""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.editor import EditorAgent, EditorResult
from backend.app.agents.highlights import HighlightData, HighlightsResult
from backend.app.db.models import AgentEvent, Call, Clip


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_highlights(call: Call) -> HighlightsResult:
    return HighlightsResult(
        call_id=call.id,
        highlights=[
            HighlightData(
                db_id=1, start_ms=10_000, end_ms=25_000,
                reason="frustration spike detected", score=0.87,
                transcript_snippet="Pay now or be arrested!",
            ),
            HighlightData(
                db_id=2, start_ms=60_000, end_ms=75_000,
                reason="comedic stall", score=0.91,
                transcript_snippet="Mr. Whiskers, get off the table!",
            ),
        ],
    )


@pytest.fixture(autouse=True)
def cleanup_clips():
    """Remove any clips/ directory written during tests."""
    yield
    clips = Path("clips")
    if clips.exists():
        shutil.rmtree(clips)


# ── Return type ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_returns_editor_result(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert isinstance(result, EditorResult)


# ── File on disk ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_exists_on_disk(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert Path(result.file_path).exists()


@pytest.mark.asyncio
async def test_file_has_mp4_extension(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert result.file_path.endswith(".mp4")


@pytest.mark.asyncio
async def test_file_path_contains_call_id(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert str(call.id) in result.file_path


# ── Status ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_is_ready_or_stub(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert result.status in ("ready", "stub")


@pytest.mark.asyncio
async def test_status_ready_when_ffmpeg_available(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed — skipping ready-status test")
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert result.status == "ready"


@pytest.mark.asyncio
async def test_status_stub_when_ffmpeg_absent(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    if shutil.which("ffmpeg") is not None:
        pytest.skip("ffmpeg IS installed — skipping stub-path test")
    result = await EditorAgent(db).run(call.id, mock_highlights)
    assert result.status == "stub"


# ── Duration ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duration_is_sum_of_highlights(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    # (25000-10000 + 75000-60000) / 1000 = 30.0 s
    result = await EditorAgent(db).run(call.id, mock_highlights)
    expected = sum(h.end_ms - h.start_ms for h in mock_highlights.highlights) / 1000.0
    assert result.duration_seconds == pytest.approx(expected)


# ── DB persistence ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persists_clip_row(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)

    q = await db.execute(select(Clip).where(Clip.id == result.db_id))
    clip = q.scalar_one()
    assert clip.call_id == call.id
    assert clip.status == result.status
    assert clip.file_path == result.file_path


@pytest.mark.asyncio
async def test_persists_agent_event(
    db: AsyncSession, call: Call, mock_highlights: HighlightsResult
) -> None:
    result = await EditorAgent(db).run(call.id, mock_highlights)

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "editor",
        )
    )
    event = q.scalar_one()
    assert event.event_type == "clip_written"
    assert event.payload["clip_id"] == result.db_id
    assert event.payload["highlight_count"] == 2


@pytest.mark.asyncio
async def test_empty_highlights_still_writes_file(
    db: AsyncSession, call: Call
) -> None:
    empty = HighlightsResult(call_id=call.id, highlights=[])
    result = await EditorAgent(db).run(call.id, empty)
    assert Path(result.file_path).exists()
    assert result.duration_seconds == pytest.approx(0.0)

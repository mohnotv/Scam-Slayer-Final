"""
Integration tests for POST /api/calls/simulate.

Uses the `client` fixture (httpx AsyncClient → FastAPI app with in-memory DB)
and patches all six agents so the test runs without any LLM or file I/O.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Call, Clip, Highlight, TranscriptSegment

UTTERANCES = [
    "Hello, this is the IRS. You owe $3,000 in back taxes.",
    "If you don't pay now you will be arrested today.",
]

SIMULATE_PAYLOAD = {"scammer_utterances": UTTERANCES}


# ── Shared patch context ───────────────────────────────────────────────────────

def _agent_patches():
    """Return a list of (target, mock) pairs covering all six agents."""
    from backend.app.agents.classifier import ClassifierAgent
    from backend.app.agents.dialogue import DialogueAgent
    from backend.app.agents.editor import EditorAgent
    from backend.app.agents.highlights import HighlightMinerAgent
    from backend.app.agents.persona import PersonaAgent
    from backend.app.agents.social import SocialAgent

    classifier_result = MagicMock(is_scam=True, confidence=0.92, scam_type="irs_impersonation")
    persona_result = MagicMock(
        db_id=1,
        age=78,
        backstory="Retired schoolteacher",
        speech_tics="Oh my stars",
        elevenlabs_voice_id="EXAVITQu4vr4xnSDxMaL",
        scam_types=["irs_impersonation"],
    )
    persona_result.name = "Grandma Betty"  # MagicMock(name=) sets internal repr, not attribute
    dialogue_result = MagicMock(utterance="Oh my stars, let me get my reading glasses…", turn_index=0, mocked=True)

    from backend.app.agents.highlights import HighlightData, HighlightsResult

    highlights_result = HighlightsResult(
        call_id=1,
        highlights=[
            HighlightData(db_id=1, start_ms=0, end_ms=3000, reason="frustration spike", score=0.91, transcript_snippet="You owe $3,000"),
        ],
    )
    editor_result = MagicMock(db_id=1, file_path="/tmp/test_clip.mp4", duration_seconds=3.0, status="stub")
    social_result = MagicMock(caption="Betty strikes again!", hashtags=["#scambaiting"], suggested_post_time="8pm ET")

    return [
        ("backend.app.routes.calls.ClassifierAgent", classifier_result),
        ("backend.app.routes.calls.PersonaAgent", persona_result),
        ("backend.app.routes.calls.DialogueAgent", dialogue_result),
        ("backend.app.routes.calls.HighlightMinerAgent", highlights_result),
        ("backend.app.routes.calls.EditorAgent", editor_result),
        ("backend.app.routes.calls.SocialAgent", social_result),
    ]


def _make_agent_class_mock(run_return):
    """Return a class mock whose instances return `run_return` from async run()."""
    instance = MagicMock()
    instance.run = AsyncMock(return_value=run_return)
    cls = MagicMock(return_value=instance)
    return cls


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulate_returns_201(client: AsyncClient):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_simulate_response_shape(client: AsyncClient):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    data = r.json()
    assert "call_id" in data
    assert "persona_name" in data
    assert "is_scam" in data
    assert "confidence" in data
    assert "scam_type" in data
    assert "duration_seconds" in data
    assert "transcript" in data
    assert "highlights" in data


@pytest.mark.asyncio
async def test_simulate_creates_call_row(client: AsyncClient, db: AsyncSession):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    assert call is not None
    assert call.status == "ended"
    assert call.twilio_call_sid.startswith("SIM_")


@pytest.mark.asyncio
async def test_simulate_creates_transcript_segments(client: AsyncClient, db: AsyncSession):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    result = await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.call_id == call_id)
    )
    segments = result.scalars().all()
    # 2 utterances × 2 speakers (scammer + persona) = 4 segments
    assert len(segments) == 4
    speakers = {s.speaker for s in segments}
    assert "scammer" in speakers
    assert "persona" in speakers


@pytest.mark.asyncio
async def test_simulate_duration_matches_utterance_count(client: AsyncClient):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    # 2 utterances × 2000 ms/turn ÷ 1000 = 4 seconds
    assert r.json()["duration_seconds"] == 4


@pytest.mark.asyncio
async def test_simulate_rejects_empty_utterances(client: AsyncClient):
    r = await client.post("/api/calls/simulate", json={"scammer_utterances": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_simulate_call_appears_in_list(client: AsyncClient):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    list_r = await client.get("/api/calls")
    assert list_r.status_code == 200
    ids = [c["id"] for c in list_r.json()]
    assert call_id in ids


@pytest.mark.asyncio
async def test_simulate_call_detail_endpoint(client: AsyncClient):
    patches = _agent_patches()
    with (
        patch("backend.app.routes.calls.ClassifierAgent", _make_agent_class_mock(patches[0][1])),
        patch("backend.app.routes.calls.PersonaAgent", _make_agent_class_mock(patches[1][1])),
        patch("backend.app.routes.calls.DialogueAgent", _make_agent_class_mock(patches[2][1])),
        patch("backend.app.routes.calls.HighlightMinerAgent", _make_agent_class_mock(patches[3][1])),
        patch("backend.app.routes.calls.EditorAgent", _make_agent_class_mock(patches[4][1])),
        patch("backend.app.routes.calls.SocialAgent", _make_agent_class_mock(patches[5][1])),
    ):
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    detail_r = await client.get(f"/api/calls/{call_id}")
    assert detail_r.status_code == 200
    detail = detail_r.json()
    assert detail["id"] == call_id
    assert "transcript" in detail
    assert "highlights" in detail
    assert len(detail["transcript"]) == 4

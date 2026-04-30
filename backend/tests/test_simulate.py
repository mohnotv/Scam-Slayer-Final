"""
Integration tests for POST /api/calls/simulate.

Uses the `client` fixture (httpx AsyncClient → FastAPI app with in-memory DB)
and patches all six agents so the test runs without any LLM or file I/O.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Call, TranscriptSegment

UTTERANCES = [
    "Hello, this is the IRS. You owe $3,000 in back taxes.",
    "If you don't pay now you will be arrested today.",
]

SIMULATE_PAYLOAD = {"scammer_utterances": UTTERANCES}

# Route prefix for all agent imports — kept here so a rename only touches one spot.
_ROUTE = "backend.app.routes.calls"


def _make_agent_class_mock(run_return: object) -> MagicMock:
    """Return a class mock whose instances return `run_return` from async run()."""
    instance = MagicMock()
    instance.run = AsyncMock(return_value=run_return)
    instance.run_post_transcript = AsyncMock(return_value=run_return)
    return MagicMock(return_value=instance)


def _build_mocks() -> dict[str, MagicMock]:
    """Construct one set of agent mocks for a single test."""
    from backend.app.agents.highlights import HighlightData, HighlightsResult

    classifier = MagicMock(
        is_scam=True, confidence=0.92, scam_type="irs_impersonation"
    )
    persona = MagicMock(
        db_id=1,
        age=78,
        backstory="Retired schoolteacher",
        speech_tics="Oh my stars",
        elevenlabs_voice_id="EXAVITQu4vr4xnSDxMaL",
        scam_types=["irs_impersonation"],
    )
    # MagicMock(name=...) sets the mock's repr, not its .name attribute.
    persona.name = "Grandma Betty"

    dialogue = MagicMock(
        utterance="Oh my stars, let me get my reading glasses…",
        turn_index=0,
        mocked=True,
    )
    highlights = HighlightsResult(
        call_id=1,
        highlights=[
            HighlightData(
                db_id=1,
                start_ms=0,
                end_ms=3000,
                reason="frustration spike",
                score=0.91,
                transcript_snippet="You owe $3,000",
            )
        ],
    )
    editor = MagicMock(
        db_id=1, file_path="/tmp/test_clip.mp4", duration_seconds=3.0, status="stub"
    )
    social = MagicMock(
        caption="Betty strikes again!",
        hashtags=["#scambaiting"],
        suggested_post_time="8pm ET",
    )

    return {
        "ClassifierAgent": _make_agent_class_mock(classifier),
        "PersonaAgent": _make_agent_class_mock(persona),
        "DialogueAgent": _make_agent_class_mock(dialogue),
        "HighlightMinerAgent": _make_agent_class_mock(highlights),
        "EditorAgent": _make_agent_class_mock(editor),
        "SocialAgent": _make_agent_class_mock(social),
    }


@contextmanager
def _patched_agents():
    """Patch all six agent classes in the calls route module."""
    mocks = _build_mocks()
    with (
        patch(f"{_ROUTE}.ClassifierAgent", mocks["ClassifierAgent"]),
        patch(f"{_ROUTE}.PersonaAgent", mocks["PersonaAgent"]),
        patch(f"{_ROUTE}.DialogueAgent", mocks["DialogueAgent"]),
        patch(f"{_ROUTE}.HighlightMinerAgent", mocks["HighlightMinerAgent"]),
        patch(f"{_ROUTE}.EditorAgent", mocks["EditorAgent"]),
        patch(f"{_ROUTE}.SocialAgent", mocks["SocialAgent"]),
    ):
        yield


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulate_returns_201(client: AsyncClient) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_simulate_response_shape(client: AsyncClient) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)
    data = r.json()
    for key in ("call_id", "persona_name", "is_scam", "confidence",
                "scam_type", "duration_seconds", "transcript", "highlights"):
        assert key in data, f"missing key: {key}"


@pytest.mark.asyncio
async def test_simulate_creates_call_row(
    client: AsyncClient, db: AsyncSession
) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    assert call is not None
    assert call.status == "ended"
    assert call.twilio_call_sid.startswith("SIM_")


@pytest.mark.asyncio
async def test_simulate_creates_transcript_segments(
    client: AsyncClient, db: AsyncSession
) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    result = await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.call_id == call_id)
    )
    segments = result.scalars().all()
    # 2 utterances × 2 speakers (scammer + persona) = 4 segments
    assert len(segments) == 4
    speakers = {s.speaker for s in segments}
    assert speakers == {"scammer", "persona"}


@pytest.mark.asyncio
async def test_simulate_duration_matches_utterance_count(
    client: AsyncClient,
) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)
    # 2 utterances × 2000 ms/turn ÷ 1000 = 4 seconds
    assert r.json()["duration_seconds"] == 4


@pytest.mark.asyncio
async def test_simulate_rejects_empty_utterances(client: AsyncClient) -> None:
    r = await client.post("/api/calls/simulate", json={"scammer_utterances": []})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_simulate_call_appears_in_list(client: AsyncClient) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    list_r = await client.get("/api/calls")
    assert list_r.status_code == 200
    assert call_id in [c["id"] for c in list_r.json()]


@pytest.mark.asyncio
async def test_simulate_call_detail_endpoint(client: AsyncClient) -> None:
    with _patched_agents():
        r = await client.post("/api/calls/simulate", json=SIMULATE_PAYLOAD)

    call_id = r.json()["call_id"]
    detail_r = await client.get(f"/api/calls/{call_id}")
    assert detail_r.status_code == 200
    detail = detail_r.json()
    assert detail["id"] == call_id
    assert "transcript" in detail
    assert "highlights" in detail
    assert len(detail["transcript"]) == 4

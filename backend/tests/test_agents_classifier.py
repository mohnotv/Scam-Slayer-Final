"""
Classifier Agent tests.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.classifier import ClassifierAgent, ClassifierResult
from backend.app.db.models import AgentEvent, Call, TranscriptSegment


@pytest.mark.asyncio
async def test_run_returns_classifier_result(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run(call.id, "+15005550006")
    assert isinstance(result, ClassifierResult)


@pytest.mark.asyncio
async def test_mock_always_flags_scam(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run(call.id, "+10000000000")
    assert result.is_scam is True


@pytest.mark.asyncio
async def test_mock_confidence_is_0_87(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run(call.id, "+15005550006")
    assert result.confidence == pytest.approx(0.87)


@pytest.mark.asyncio
async def test_mock_scam_type(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run(call.id, "+15005550006")
    assert result.scam_type == "irs_impersonation"


@pytest.mark.asyncio
async def test_confidence_in_range(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run(call.id, "+15005550006")
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_persists_agent_event(db: AsyncSession, call: Call) -> None:
    from sqlalchemy import select

    await ClassifierAgent(db).run(call.id, "+15005550006")

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "classifier",
        )
    )
    events = q.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "classification_complete"
    assert events[0].payload["is_scam"] is True
    assert events[0].payload["mocked"] is True


@pytest.mark.asyncio
async def test_audio_bytes_flag_in_event(db: AsyncSession, call: Call) -> None:
    from sqlalchemy import select

    await ClassifierAgent(db).run(call.id, "+15005550006", audio_bytes=b"\xff\xfe")

    q = await db.execute(select(AgentEvent).where(AgentEvent.call_id == call.id))
    event = q.scalar_one()
    assert event.payload["audio_provided"] is True


@pytest.mark.asyncio
async def test_no_audio_flag_in_event(db: AsyncSession, call: Call) -> None:
    from sqlalchemy import select

    await ClassifierAgent(db).run(call.id, "+15005550006", audio_bytes=None)

    q = await db.execute(select(AgentEvent).where(AgentEvent.call_id == call.id))
    event = q.scalar_one()
    assert event.payload["audio_provided"] is False


@pytest.mark.asyncio
async def test_run_post_transcript_empty(db: AsyncSession, call: Call) -> None:
    result = await ClassifierAgent(db).run_post_transcript(call.id, "+1")
    assert result.scam_type == "unknown"
    assert result.is_scam is False


@pytest.mark.asyncio
async def test_run_post_transcript_heuristic_when_llm_fails(db: AsyncSession, call: Call) -> None:
    db.add(
        TranscriptSegment(
            call_id=call.id,
            speaker="scammer",
            text="This is the IRS, you owe back taxes and must pay today.",
            timestamp_ms=0,
            is_final=True,
            confidence=1.0,
        )
    )
    await db.commit()

    with patch(
        "backend.app.agents.classifier.generate_text",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no llm"),
    ):
        result = await ClassifierAgent(db).run_post_transcript(call.id, "+1")

    assert result.scam_type == "irs_impersonation"
    assert result.is_scam is True

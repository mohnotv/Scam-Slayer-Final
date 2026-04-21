"""
Database layer tests.

Tests table creation, all five ORM models, FK relationships, and the
session factory helper.  Everything runs against an in-memory SQLite DB
(fixtures from conftest.py) — no files are written to disk.
"""

import json

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import (
    AgentEvent,
    Base,
    Call,
    Clip,
    Highlight,
    Persona,
    TranscriptSegment,
)


# ── Table creation ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_tables_created(db_engine) -> None:
    """init_db (via the fixture) must create every expected table."""
    expected = {
        "personas",
        "calls",
        "transcript_segments",
        "highlights",
        "clips",
        "agent_events",
    }
    async with db_engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )
    assert expected <= table_names, f"Missing tables: {expected - table_names}"


# ── Persona ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_fetch_persona(db: AsyncSession) -> None:
    persona = Persona(
        name="Grandma Betty",
        backstory="Retired schoolteacher from Tulsa.",
        speech_tics="Says 'Oh my stars!'",
        elevenlabs_voice_id="EXAVITQu4vr4xnSDxMaL",
        scam_types=json.dumps(["irs_impersonation", "tech_support"]),
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)

    assert persona.id is not None
    result = await db.execute(select(Persona).where(Persona.id == persona.id))
    fetched = result.scalar_one()
    assert fetched.name == "Grandma Betty"
    assert fetched.scam_types_list == ["irs_impersonation", "tech_support"]


@pytest.mark.asyncio
async def test_persona_name_is_unique(db: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    db.add(Persona(name="Duplicate", backstory="first"))
    await db.commit()

    db.add(Persona(name="Duplicate", backstory="second"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ── Call ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_call_without_persona(db: AsyncSession) -> None:
    call = Call(twilio_call_sid="CA_test_001", caller_number="+15005550006")
    db.add(call)
    await db.commit()
    await db.refresh(call)

    assert call.id is not None
    assert call.status == "active"
    assert call.is_scam is False
    assert call.persona_id is None


@pytest.mark.asyncio
async def test_call_linked_to_persona(db: AsyncSession) -> None:
    persona = Persona(name="Frank", backstory="Retired plumber.")
    db.add(persona)
    await db.commit()
    await db.refresh(persona)

    call = Call(twilio_call_sid="CA_test_002", persona_id=persona.id)
    db.add(call)
    await db.commit()
    await db.refresh(call)

    result = await db.execute(select(Call).where(Call.id == call.id))
    fetched = result.scalar_one()
    assert fetched.persona_id == persona.id


@pytest.mark.asyncio
async def test_call_sid_is_unique(db: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    db.add(Call(twilio_call_sid="CA_dup"))
    await db.commit()
    db.add(Call(twilio_call_sid="CA_dup"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


# ── TranscriptSegment ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_transcript_segments(db: AsyncSession, call: Call) -> None:
    segments = [
        TranscriptSegment(
            call_id=call.id,
            speaker="scammer",
            text="Hello, this is the IRS.",
            timestamp_ms=1200,
            is_final=True,
            confidence=0.98,
        ),
        TranscriptSegment(
            call_id=call.id,
            speaker="persona",
            text="Oh my stars, the IRS! Let me find my glasses.",
            timestamp_ms=3500,
            is_final=True,
            confidence=1.0,
        ),
    ]
    for s in segments:
        db.add(s)
    await db.commit()

    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.call_id == call.id)
        .order_by(TranscriptSegment.timestamp_ms)
    )
    fetched = result.scalars().all()
    assert len(fetched) == 2
    assert fetched[0].speaker == "scammer"
    assert fetched[1].speaker == "persona"
    assert fetched[0].confidence == pytest.approx(0.98)


@pytest.mark.asyncio
async def test_partial_and_final_segments(db: AsyncSession, call: Call) -> None:
    """Partial (is_final=False) segments should coexist with final ones."""
    db.add(TranscriptSegment(
        call_id=call.id, speaker="scammer", text="You owe", timestamp_ms=500, is_final=False
    ))
    db.add(TranscriptSegment(
        call_id=call.id, speaker="scammer", text="You owe back taxes.", timestamp_ms=500, is_final=True
    ))
    await db.commit()

    result = await db.execute(
        select(TranscriptSegment).where(
            TranscriptSegment.call_id == call.id,
            TranscriptSegment.is_final == True,  # noqa: E712
        )
    )
    finals = result.scalars().all()
    assert len(finals) == 1


# ── Highlight ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_fetch_highlight(db: AsyncSession, call: Call) -> None:
    h = Highlight(
        call_id=call.id,
        start_ms=12_000,
        end_ms=27_000,
        reason="Scammer frustration spike",
        score=0.87,
        transcript_snippet="You must pay NOW!",
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)

    result = await db.execute(select(Highlight).where(Highlight.call_id == call.id))
    fetched = result.scalar_one()
    assert fetched.start_ms == 12_000
    assert fetched.score == pytest.approx(0.87)
    assert fetched.reason == "Scammer frustration spike"


# ── Clip ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_clip_defaults(db: AsyncSession, call: Call) -> None:
    clip = Clip(call_id=call.id)
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    assert clip.id is not None
    assert clip.status == "pending"
    assert clip.caption == ""
    assert clip.hashtags == "[]"


@pytest.mark.asyncio
async def test_clip_status_transitions(db: AsyncSession, call: Call) -> None:
    clip = Clip(call_id=call.id, status="pending")
    db.add(clip)
    await db.commit()

    clip.status = "ready"
    clip.caption = "Betty kept a scammer on for 7 minutes 😭"
    db.add(clip)
    await db.commit()

    result = await db.execute(select(Clip).where(Clip.id == clip.id))
    fetched = result.scalar_one()
    assert fetched.status == "ready"
    assert "Betty" in fetched.caption


# ── AgentEvent ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_event_stores_json_payload(db: AsyncSession, call: Call) -> None:
    event = AgentEvent(
        call_id=call.id,
        agent="classifier",
        event_type="classification_complete",
        payload={"is_scam": True, "confidence": 0.95, "scam_type": "irs_impersonation"},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    result = await db.execute(select(AgentEvent).where(AgentEvent.call_id == call.id))
    fetched = result.scalar_one()
    assert fetched.agent == "classifier"
    assert fetched.payload["is_scam"] is True
    assert fetched.payload["confidence"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_multiple_agent_events_ordered(db: AsyncSession, call: Call) -> None:
    agents = ["classifier", "persona", "dialogue", "highlights"]
    for agent in agents:
        db.add(AgentEvent(call_id=call.id, agent=agent, event_type="test", payload={}))
    await db.commit()

    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.call_id == call.id)
        .order_by(AgentEvent.created_at)
    )
    events = result.scalars().all()
    assert [e.agent for e in events] == agents


# ── Relationships ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_relationships_accessible(db: AsyncSession, call: Call) -> None:
    """Verify that all relationship attributes on Call are queryable."""
    db.add(TranscriptSegment(call_id=call.id, speaker="scammer", text="Hello", timestamp_ms=0, is_final=True))
    db.add(Highlight(call_id=call.id, start_ms=0, end_ms=5000, score=0.5))
    db.add(Clip(call_id=call.id))
    db.add(AgentEvent(call_id=call.id, agent="test", event_type="test", payload={}))
    await db.commit()

    # Re-fetch call with all relationships eager-loaded via selectin
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Call)
        .options(
            selectinload(Call.transcript_segments),
            selectinload(Call.highlights),
            selectinload(Call.clips),
            selectinload(Call.agent_events),
        )
        .where(Call.id == call.id)
    )
    fetched = result.scalar_one()

    assert len(fetched.transcript_segments) == 1
    assert len(fetched.highlights) == 1
    assert len(fetched.clips) == 1
    assert len(fetched.agent_events) == 1

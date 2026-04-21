"""
Calls REST API

GET  /calls              — paginated list of all calls
GET  /calls/{id}         — single call with persona info
GET  /calls/{id}/transcript  — ordered transcript rows
GET  /calls/{id}/highlights  — highlight rows with scores
GET  /calls/{id}/events  — agent event log (for dashboard replay)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Call, Highlight, Transcript
from backend.app.db.session import get_db

router = APIRouter(prefix="/calls", tags=["calls"])


class CallSummary(BaseModel):
    id: int
    twilio_call_sid: str
    caller_number: str
    is_scam: bool
    scam_confidence: float
    scam_type: str
    status: str
    duration_seconds: int
    persona_name: str | None

    model_config = {"from_attributes": True}


class TranscriptRow(BaseModel):
    id: int
    speaker: str
    text: str
    timestamp_ms: int
    is_final: bool

    model_config = {"from_attributes": True}


class HighlightRow(BaseModel):
    id: int
    start_ms: int
    end_ms: int
    reason: str
    score: float
    transcript_snippet: str

    model_config = {"from_attributes": True}


class EventRow(BaseModel):
    id: int
    agent: str
    event_type: str
    payload: dict
    created_at: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CallSummary])
async def list_calls(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[CallSummary]:
    result = await db.execute(
        select(Call).order_by(Call.started_at.desc()).offset(skip).limit(limit)
    )
    calls = result.scalars().all()
    out = []
    for c in calls:
        persona_name = c.persona.name if c.persona else None
        out.append(CallSummary(
            id=c.id,
            twilio_call_sid=c.twilio_call_sid,
            caller_number=c.caller_number,
            is_scam=c.is_scam,
            scam_confidence=c.scam_confidence,
            scam_type=c.scam_type,
            status=c.status,
            duration_seconds=c.duration_seconds,
            persona_name=persona_name,
        ))
    return out


@router.get("/{call_id}", response_model=CallSummary)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)) -> CallSummary:
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    persona_name = call.persona.name if call.persona else None
    return CallSummary(
        id=call.id,
        twilio_call_sid=call.twilio_call_sid,
        caller_number=call.caller_number,
        is_scam=call.is_scam,
        scam_confidence=call.scam_confidence,
        scam_type=call.scam_type,
        status=call.status,
        duration_seconds=call.duration_seconds,
        persona_name=persona_name,
    )


@router.get("/{call_id}/transcript", response_model=list[TranscriptRow])
async def get_transcript(call_id: int, db: AsyncSession = Depends(get_db)) -> list[TranscriptRow]:
    result = await db.execute(
        select(Transcript)
        .where(Transcript.call_id == call_id)
        .order_by(Transcript.timestamp_ms)
    )
    return [TranscriptRow.model_validate(r) for r in result.scalars().all()]


@router.get("/{call_id}/highlights", response_model=list[HighlightRow])
async def get_highlights(call_id: int, db: AsyncSession = Depends(get_db)) -> list[HighlightRow]:
    result = await db.execute(
        select(Highlight)
        .where(Highlight.call_id == call_id)
        .order_by(Highlight.score.desc())
    )
    return [HighlightRow.model_validate(r) for r in result.scalars().all()]


@router.get("/{call_id}/events", response_model=list[EventRow])
async def get_events(call_id: int, db: AsyncSession = Depends(get_db)) -> list[EventRow]:
    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.call_id == call_id)
        .order_by(AgentEvent.created_at)
    )
    rows = result.scalars().all()
    return [
        EventRow(
            id=r.id,
            agent=r.agent,
            event_type=r.event_type,
            payload=r.payload,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]

"""
Calls REST API  (mounted at /api/calls by main.py)

POST /simulate          — run a full mock call pipeline from a list of scammer utterances
GET  /                  — list calls (id, start time, duration, persona, highlight count)
GET  /{id}              — full call detail with transcript, highlights, clip
GET  /{id}/clip         — stream the .mp4 clip file for this call
GET  /{id}/transcript   — ordered transcript segments
GET  /{id}/highlights   — highlights ordered by virality score desc
GET  /{id}/events       — agent event log for dashboard replay
"""

import json as _json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.agents.classifier import ClassifierAgent
from backend.app.agents.dialogue import DialogueAgent
from backend.app.agents.editor import EditorAgent
from backend.app.agents.highlights import HighlightMinerAgent
from backend.app.agents.persona import PersonaAgent
from backend.app.agents.social import SocialAgent
from backend.app.config import settings
from backend.app.db.models import AgentEvent, Call, Clip, Highlight, TranscriptSegment
from backend.app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calls", tags=["calls"])

# ── Shared response models ─────────────────────────────────────────────────────


class TranscriptRow(BaseModel):
    id: int
    speaker: str
    text: str
    timestamp_ms: int
    is_final: bool
    confidence: float

    model_config = {"from_attributes": True}


class HighlightRow(BaseModel):
    id: int
    start_ms: int
    end_ms: int
    reason: str
    score: float
    transcript_snippet: str

    model_config = {"from_attributes": True}


class ClipOut(BaseModel):
    id: int
    call_id: int
    file_path: str
    duration_seconds: float
    caption: str
    hashtags: list[str]
    status: str

    model_config = {"from_attributes": True}


class EventRow(BaseModel):
    id: int
    agent: str
    event_type: str
    payload: dict[str, object]
    created_at: str

    model_config = {"from_attributes": True}


# ── /simulate specific models ─────────────────────────────────────────────────


class SimulateRequest(BaseModel):
    scammer_utterances: list[str] = Field(
        min_length=1,
        description="Ordered list of things the scammer says. Betty responds to each.",
    )
    persona_name: str | None = None


class SimulateResponse(BaseModel):
    call_id: int
    persona_name: str
    is_scam: bool
    confidence: float
    scam_type: str
    duration_seconds: int
    transcript: list[TranscriptRow]
    highlights: list[HighlightRow]
    clip: ClipOut | None


# ── GET / list models ─────────────────────────────────────────────────────────


class CallListItem(BaseModel):
    id: int
    caller_number: str
    started_at: str
    duration_seconds: int
    persona_name: str | None
    is_scam: bool
    scam_type: str
    status: str
    highlight_count: int
    clip_id: int | None


# ── GET /{id} detail model ────────────────────────────────────────────────────


class CallDetail(BaseModel):
    id: int
    twilio_call_sid: str
    caller_number: str
    is_scam: bool
    scam_confidence: float
    scam_type: str
    status: str
    duration_seconds: int
    started_at: str
    ended_at: str | None
    persona_name: str | None
    transcript: list[TranscriptRow]
    highlights: list[HighlightRow]
    clip_url: str | None   # relative URL to stream the file
    clip: ClipOut | None
    recording_available: bool = False
    recording_duration_seconds: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clip_orm_to_out(c: Clip) -> ClipOut:
    return ClipOut(
        id=c.id,
        call_id=c.call_id,
        file_path=c.file_path,
        duration_seconds=c.duration_seconds,
        caption=c.caption,
        hashtags=_json.loads(c.hashtags) if c.hashtags else [],
        status=c.status,
    )


async def _require_call(call_id: int, db: AsyncSession) -> Call:
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


# ── POST /simulate ─────────────────────────────────────────────────────────────


@router.post("/simulate", response_model=SimulateResponse, status_code=201)
async def simulate_call(
    body: SimulateRequest,
    db: AsyncSession = Depends(get_db),
) -> SimulateResponse:
    """
    Run the full six-agent pipeline synchronously against a list of scripted
    scammer utterances.  No Twilio connection required — useful for demos and CI.

    Pipeline:
      1. Create a Call row (twilio_call_sid = "SIM_<uuid>")
      2. PersonaAgent     → select persona (scam_type unknown until transcript exists)
      3. For each utterance:
             a. Write scammer TranscriptSegment
             b. DialogueAgent → Betty's response
             c. Write persona TranscriptSegment
      4. ClassifierAgent.run_post_transcript → is_scam, scam_type from full transcript
      5. Mark Call ended, set duration
      6. HighlightMinerAgent  → 3 highlights
      7. EditorAgent          → placeholder .mp4
      8. SocialAgent          → caption + hashtags
      9. Return full SimulateResponse
    """
    sim_sid = f"SIM_{uuid.uuid4().hex[:12].upper()}"

    # ── 1. Create Call ────────────────────────────────────────────────────────
    call = Call(
        twilio_call_sid=sim_sid,
        caller_number="SIMULATED",
        status="active",
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    # ── 2. Persona (no pre-call scam triage — persona reacts to dialogue only) ─
    persona = await PersonaAgent(db).run(
        call.id,
        "unknown",
        persona_name=body.persona_name,
    )
    call.persona_id = persona.db_id
    db.add(call)
    await db.commit()

    # ── 3. Dialogue loop ──────────────────────────────────────────────────────
    dialogue_agent = DialogueAgent(db)
    history: list[dict[str, str]] = []
    # Simulate 2 s per turn (1 s scammer + 1 s Betty)
    ms_per_turn = 2_000

    for turn, utterance in enumerate(body.scammer_utterances):
        scammer_ts = turn * ms_per_turn

        db.add(TranscriptSegment(
            call_id=call.id,
            speaker="scammer",
            text=utterance,
            timestamp_ms=scammer_ts,
            is_final=True,
            confidence=1.0,
        ))
        await db.commit()

        dialogue_result = await dialogue_agent.run(call.id, persona, history, utterance)
        history.append({"role": "user", "content": utterance})
        history.append({"role": "assistant", "content": dialogue_result.utterance})

        db.add(TranscriptSegment(
            call_id=call.id,
            speaker="persona",
            text=dialogue_result.utterance,
            timestamp_ms=scammer_ts + 1_000,
            is_final=True,
            confidence=1.0,
        ))
        await db.commit()

    # ── 4. Classify from transcript (after persona dialogue) ──────────────────
    classification = await ClassifierAgent(db).run_post_transcript(call.id, "SIMULATED")
    call.is_scam = classification.is_scam
    call.scam_confidence = classification.confidence
    call.scam_type = classification.scam_type
    db.add(call)
    await db.commit()

    # ── 5. Close call ─────────────────────────────────────────────────────────
    duration_seconds = len(body.scammer_utterances) * ms_per_turn // 1000
    call.ended_at = datetime.utcnow()
    call.status = "ended"
    call.duration_seconds = duration_seconds
    db.add(call)
    await db.commit()

    # ── 6. Highlights ─────────────────────────────────────────────────────────
    highlights_result = await HighlightMinerAgent(db).run(call.id)

    # ── 7. Editor ─────────────────────────────────────────────────────────────
    editor_result = await EditorAgent(db).run(call.id, highlights_result)

    # ── 8. Social ─────────────────────────────────────────────────────────────
    await SocialAgent(db).run(
        call_id=call.id,
        clip_db_id=editor_result.db_id,
        clip_duration_seconds=editor_result.duration_seconds,
        call_duration_seconds=duration_seconds,
        highlights=highlights_result,
    )

    # ── 9. Build response from DB ─────────────────────────────────────────────
    seg_q = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.call_id == call.id)
        .order_by(TranscriptSegment.timestamp_ms)
    )
    segments = seg_q.scalars().all()

    hl_q = await db.execute(
        select(Highlight)
        .where(Highlight.call_id == call.id)
        .order_by(Highlight.score.desc())
    )
    highlights_orm = hl_q.scalars().all()

    clip_q = await db.execute(
        select(Clip).where(Clip.call_id == call.id).order_by(Clip.created_at.desc())
    )
    clip_orm = clip_q.scalars().first()

    return SimulateResponse(
        call_id=call.id,
        persona_name=persona.name,
        is_scam=call.is_scam,
        confidence=call.scam_confidence,
        scam_type=call.scam_type,
        duration_seconds=call.duration_seconds,
        transcript=[TranscriptRow.model_validate(s) for s in segments],
        highlights=[HighlightRow.model_validate(h) for h in highlights_orm],
        clip=_clip_orm_to_out(clip_orm) if clip_orm else None,
    )


# ── GET / ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[CallListItem])
async def list_calls(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[CallListItem]:
    """List calls newest-first with highlight count and clip ID."""
    result = await db.execute(
        select(Call)
        .options(
            selectinload(Call.persona),
            selectinload(Call.highlights),
            selectinload(Call.clips),
        )
        .order_by(Call.started_at.desc())
        .offset(skip)
        .limit(limit)
    )
    calls = result.scalars().all()

    out: list[CallListItem] = []
    for c in calls:
        clip_id = c.clips[0].id if c.clips else None
        out.append(CallListItem(
            id=c.id,
            caller_number=c.caller_number,
            started_at=c.started_at.isoformat(),
            duration_seconds=c.duration_seconds,
            persona_name=c.persona.name if c.persona else None,
            is_scam=c.is_scam,
            scam_type=c.scam_type,
            status=c.status,
            highlight_count=len(c.highlights),
            clip_id=clip_id,
        ))
    return out


# ── GET /{id} ─────────────────────────────────────────────────────────────────


@router.get("/{call_id}", response_model=CallDetail)
async def get_call(call_id: int, db: AsyncSession = Depends(get_db)) -> CallDetail:
    """Full call detail — transcript, highlights, and clip metadata in one response."""
    result = await db.execute(
        select(Call)
        .options(
            selectinload(Call.persona),
            selectinload(Call.transcript_segments),
            selectinload(Call.highlights),
            selectinload(Call.clips),
        )
        .where(Call.id == call_id)
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Sort in Python to avoid extra query
    segments = sorted(call.transcript_segments, key=lambda s: s.timestamp_ms)
    highlights = sorted(call.highlights, key=lambda h: h.score, reverse=True)
    # Most recent clip
    clip_orm = max(call.clips, key=lambda c: c.created_at) if call.clips else None

    clip_url = f"/api/calls/{call_id}/clip" if clip_orm else None

    return CallDetail(
        id=call.id,
        twilio_call_sid=call.twilio_call_sid,
        caller_number=call.caller_number,
        is_scam=call.is_scam,
        scam_confidence=call.scam_confidence,
        scam_type=call.scam_type,
        status=call.status,
        duration_seconds=call.duration_seconds,
        started_at=call.started_at.isoformat(),
        ended_at=call.ended_at.isoformat() if call.ended_at else None,
        persona_name=call.persona.name if call.persona else None,
        transcript=[TranscriptRow.model_validate(s) for s in segments],
        highlights=[HighlightRow.model_validate(h) for h in highlights],
        clip_url=clip_url,
        clip=_clip_orm_to_out(clip_orm) if clip_orm else None,
        recording_available=bool((call.recording_sid or "").strip()),
        recording_duration_seconds=int(call.recording_duration_seconds or 0),
    )


# ── GET /{id}/recording ─────────────────────────────────────────────────────


@router.get("/{call_id}/recording")
async def get_call_recording(call_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    """Stream the Twilio dual-channel MP3 for a completed call (requires recording_sid)."""
    call = await _require_call(call_id, db)
    sid = (call.recording_sid or "").strip()
    if not sid:
        raise HTTPException(status_code=404, detail="No call recording available yet")

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Recordings/{sid}.mp3"
    )
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(url, auth=auth)
    if r.status_code != 200:
        logger.error("Twilio recording fetch failed: %s %s", r.status_code, (r.text or "")[:500])
        raise HTTPException(status_code=502, detail="Could not fetch recording from Twilio")

    return Response(
        content=r.content,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="call_{call_id}.mp3"',
        },
    )


# ── GET /{id}/clip ────────────────────────────────────────────────────────────


@router.get("/{call_id}/clip")
async def get_call_clip(call_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """Stream the .mp4 clip for a call (most recent clip if multiple exist)."""
    await _require_call(call_id, db)

    clip_q = await db.execute(
        select(Clip)
        .where(Clip.call_id == call_id)
        .order_by(Clip.created_at.desc())
    )
    clip = clip_q.scalars().first()

    if clip is None:
        raise HTTPException(status_code=404, detail="No clip generated for this call yet")
    if not clip.file_path or not Path(clip.file_path).exists():
        raise HTTPException(status_code=404, detail="Clip file not on disk yet")

    return FileResponse(
        clip.file_path,
        media_type="video/mp4",
        filename=Path(clip.file_path).name,
    )


# ── GET /{id}/transcript ──────────────────────────────────────────────────────


@router.get("/{call_id}/transcript", response_model=list[TranscriptRow])
async def get_transcript(
    call_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[TranscriptRow]:
    await _require_call(call_id, db)
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.call_id == call_id)
        .order_by(TranscriptSegment.timestamp_ms)
    )
    return [TranscriptRow.model_validate(r) for r in result.scalars().all()]


# ── GET /{id}/highlights ──────────────────────────────────────────────────────


@router.get("/{call_id}/highlights", response_model=list[HighlightRow])
async def get_highlights(
    call_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[HighlightRow]:
    await _require_call(call_id, db)
    result = await db.execute(
        select(Highlight)
        .where(Highlight.call_id == call_id)
        .order_by(Highlight.score.desc())
    )
    return [HighlightRow.model_validate(r) for r in result.scalars().all()]


# ── GET /{id}/events ──────────────────────────────────────────────────────────


@router.get("/{call_id}/events", response_model=list[EventRow])
async def get_events(
    call_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[EventRow]:
    await _require_call(call_id, db)
    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.call_id == call_id)
        .order_by(AgentEvent.created_at)
    )
    return [
        EventRow(
            id=r.id,
            agent=r.agent,
            event_type=r.event_type,
            payload=r.payload,
            created_at=r.created_at.isoformat(),
        )
        for r in result.scalars().all()
    ]

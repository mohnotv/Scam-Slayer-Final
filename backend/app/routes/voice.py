"""
Voice routes — Twilio webhooks and Media Stream WebSocket.

POST /voice/incoming  — called by Twilio when a new call arrives
WS   /voice/stream/{call_sid} — bidirectional audio stream (mulaw 8kHz)
POST /voice/status    — Twilio call-status callback (ended, failed, etc.)
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.classifier import classify_call
from backend.app.agents.dialogue import generate_response
from backend.app.agents.highlights import mine_highlights
from backend.app.agents.persona import select_persona
from backend.app.db.models import Call, TranscriptSegment
from backend.app.db.session import get_db
from backend.app.services.twilio_client import build_stream_twiml

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/incoming")
async def incoming_call(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """
    Twilio webhook — fires the moment a call connects.
    1. Create Call row.
    2. Run Classifier Agent.
    3. Select Persona.
    4. Return TwiML to open Media Stream.
    """
    form = await request.form()
    call_sid: str = str(form.get("CallSid", "MOCK_SID"))
    caller: str = str(form.get("From", "unknown"))

    call = Call(twilio_call_sid=call_sid, caller_number=caller)
    db.add(call)
    await db.commit()
    await db.refresh(call)

    classification = await classify_call(call.id, caller, db)
    call.is_scam = classification.is_scam
    call.scam_confidence = classification.confidence
    call.scam_type = classification.scam_type
    db.add(call)

    persona = await select_persona(call.id, classification.scam_type, db)
    call.persona_id = persona.id
    db.add(call)
    await db.commit()

    twiml = build_stream_twiml(call_sid)
    return Response(content=twiml, media_type="application/xml")


@router.websocket("/stream/{call_sid}")
async def media_stream(
    websocket: WebSocket,
    call_sid: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Twilio Media Stream WebSocket.
    Receives mulaw audio from scammer, pipes to STT, sends LLM response to TTS,
    and streams TTS audio back.

    MVP: echoes mock transcript chunks and generates a real Claude response.
    """
    await websocket.accept()
    conversation_history: list[dict] = []

    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(Call).where(Call.twilio_call_sid == call_sid))
    call = result.scalar_one_or_none()
    if call is None:
        await websocket.close(code=1008)
        return

    from backend.app.db.models import Persona
    persona = None
    if call.persona_id:
        p_result = await db.execute(sa_select(Persona).where(Persona.id == call.persona_id))
        persona = p_result.scalar_one_or_none()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                # In MVP: use mock scammer text; real: pipe payload["media"]["payload"] to Deepgram
                mock_scammer_text = "You owe back taxes. You must pay or be arrested."
                segment = TranscriptSegment(
                    call_id=call.id,
                    speaker="scammer",
                    text=mock_scammer_text,
                    timestamp_ms=0,
                    is_final=True,
                    confidence=1.0,
                )
                db.add(segment)
                await db.commit()

                if persona:
                    response_text = await generate_response(
                        call.id, persona, conversation_history, mock_scammer_text, db
                    )
                    conversation_history.append({"role": "user", "content": mock_scammer_text})
                    conversation_history.append({"role": "assistant", "content": response_text})

                    reply_segment = TranscriptSegment(
                        call_id=call.id,
                        speaker="persona",
                        text=response_text,
                        timestamp_ms=0,
                        is_final=True,
                        confidence=1.0,
                    )
                    db.add(reply_segment)
                    await db.commit()

                    # TODO: synthesize via ElevenLabs and stream audio back
                    logger.info("Persona response: %s", response_text)

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        call.ended_at = datetime.utcnow()
        call.status = "ended"
        db.add(call)
        await db.commit()
        await mine_highlights(call.id, db)


@router.post("/status")
async def call_status(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Twilio status callback — update Call row when the call ends."""
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    call_status_value = str(form.get("CallStatus", ""))
    duration = int(form.get("CallDuration", 0))

    from sqlalchemy import select as sa_select
    result = await db.execute(sa_select(Call).where(Call.twilio_call_sid == call_sid))
    call = result.scalar_one_or_none()
    if call:
        call.status = call_status_value
        call.duration_seconds = duration
        call.ended_at = call.ended_at or datetime.utcnow()
        db.add(call)
        await db.commit()

    return {"ok": True}

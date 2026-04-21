"""
Voice routes — Twilio webhooks and Media Stream WebSocket.

POST /voice/incoming         — Twilio calls this when a new call arrives
WS   /voice/stream/{sid}     — bidirectional mulaw audio stream
POST /voice/status           — Twilio call-status callback (ended, failed…)
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.classifier import ClassifierAgent
from backend.app.agents.dialogue import DialogueAgent
from backend.app.agents.highlights import HighlightMinerAgent
from backend.app.agents.persona import PersonaAgent
from backend.app.config import settings
from backend.app.db.models import Call, Persona, TranscriptSegment
from backend.app.db.session import get_db
from backend.app.services.twilio_client import build_stream_twiml

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/incoming")
async def incoming_call(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio webhook — fires the moment an inbound call connects.

    Pipeline:
      1. Create Call row
      2. ClassifierAgent → is_scam + scam_type
      3. PersonaAgent    → select / create Betty
      4. Return TwiML to open Media Stream WebSocket
    """
    form = await request.form()
    call_sid: str = str(form.get("CallSid", "MOCK_SID"))
    caller: str = str(form.get("From", "unknown"))

    call = Call(twilio_call_sid=call_sid, caller_number=caller)
    db.add(call)
    await db.commit()
    await db.refresh(call)

    classification = await ClassifierAgent(db).run(call.id, caller)
    call.is_scam = classification.is_scam
    call.scam_confidence = classification.confidence
    call.scam_type = classification.scam_type

    persona_result = await PersonaAgent(db).run(call.id, classification.scam_type)
    call.persona_id = persona_result.db_id

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

    Receives JSON frames from Twilio:
      {"event": "media",  "media": {"payload": "<base64-mulaw>"}}
      {"event": "stop"}

    Mock phase behaviour:
      - Scammer audio is replaced with a fixed fixture utterance.
      - DialogueAgent is called for real (MOCK_CLAUDE=true by default).
      - TTS synthesis is skipped; the response is logged only.
    """
    await websocket.accept()
    conversation_history: list[dict[str, str]] = []

    # ── Fetch call + persona ───────────────────────────────────────────────────
    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call is None:
        await websocket.close(code=1008)
        return

    persona_data = None
    if call.persona_id:
        p_q = await db.execute(select(Persona).where(Persona.id == call.persona_id))
        persona_orm = p_q.scalar_one_or_none()
        if persona_orm:
            persona_data = PersonaAgent.orm_to_result(persona_orm)

    dialogue_agent = DialogueAgent(db)

    # ── Main receive loop ──────────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                # Real path: decode msg["media"]["payload"] → pipe to Deepgram STT
                # Mock path: use a fixed utterance so the rest of the pipeline runs
                mock_scammer_text = "You owe back taxes. Pay immediately or be arrested."

                db.add(TranscriptSegment(
                    call_id=call.id,
                    speaker="scammer",
                    text=mock_scammer_text,
                    timestamp_ms=0,
                    is_final=True,
                    confidence=1.0,
                ))
                await db.commit()

                if persona_data:
                    dialogue_result = await dialogue_agent.run(
                        call.id,
                        persona_data,
                        conversation_history,
                        mock_scammer_text,
                    )
                    conversation_history.append({"role": "user", "content": mock_scammer_text})
                    conversation_history.append({"role": "assistant", "content": dialogue_result.utterance})

                    db.add(TranscriptSegment(
                        call_id=call.id,
                        speaker="persona",
                        text=dialogue_result.utterance,
                        timestamp_ms=0,
                        is_final=True,
                        confidence=1.0,
                    ))
                    await db.commit()

                    # TODO: synthesize via ElevenLabs and stream back as base64 mulaw
                    logger.info(
                        "Persona [%s] turn %d: %s",
                        persona_data.name,
                        dialogue_result.turn_index,
                        dialogue_result.utterance[:80],
                    )

                    # Enforce max call duration
                    elapsed = (datetime.utcnow() - call.started_at).seconds
                    if elapsed >= settings.max_call_duration_seconds:
                        logger.info("Max call duration reached — closing WebSocket.")
                        break

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        call.ended_at = datetime.utcnow()
        call.status = "ended"
        if call.started_at and call.ended_at:
            call.duration_seconds = int((call.ended_at - call.started_at).total_seconds())
        db.add(call)
        await db.commit()
        # Mine highlights as soon as the call ends (runs synchronously in the WS finalizer)
        await HighlightMinerAgent(db).run(call.id)


@router.post("/status")
async def call_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Twilio status callback — keeps Call.status in sync with Twilio's truth."""
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    twilio_status = str(form.get("CallStatus", ""))
    duration = int(form.get("CallDuration", 0))

    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call:
        call.status = twilio_status
        call.duration_seconds = duration
        if not call.ended_at:
            call.ended_at = datetime.utcnow()
        db.add(call)
        await db.commit()

    return {"ok": True}

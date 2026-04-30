"""
Voice routes — Twilio webhooks and Media Stream WebSocket.

POST /voice/incoming         — Twilio calls this when a new call arrives
POST /voice/gather/{sid}     — Twilio <Gather input="speech"> callback (no Deepgram)
WS   /voice/stream/{sid}     — bidirectional mulaw audio stream
POST /voice/status           — Twilio call-status callback (ended, failed…)
POST /voice/recording/status — Twilio recording finished → stores RecordingSid on Call
"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.classifier import ClassifierAgent
from backend.app.agents.dialogue import DialogueAgent, normalize_chat_messages
from backend.app.agents.highlights import HighlightMinerAgent
from backend.app.agents.persona import PersonaAgent
from backend.app.config import settings
from backend.app.db.models import Call, Highlight, Persona, TranscriptSegment
from backend.app.db.session import get_db
from backend.app.services.twilio_client import build_gather_twiml, build_stream_twiml, twilio_say_voice_for_persona
from backend.app.services.elevenlabs_tts import tts_to_mp3_file
from backend.app.services.voice_pipeline import (
    SpeechToTextAgent,
    TextToSpeechAgent,
    persist_segment,
    ResponseGenerator,
)


def _public_https_base() -> str:
    """Twilio webhook base (must be https, publicly reachable). Empty if not configured."""
    u = (settings.ngrok_url or "").strip()
    if not u or "placeholder" in u.lower():
        return ""
    u = u.rstrip("/")
    if u.startswith("https://"):
        return u
    if u.startswith("http://"):
        return "https://" + u.removeprefix("http://").lstrip("/")
    return f"https://{u.lstrip('/')}"


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


async def _post_call_classify_and_highlights(db: AsyncSession, call: Call) -> None:
    """
    After the transcript exists: classify from conversation (not caller-ID triage),
    then mine highlights once. Skips if there are no segments or highlights already exist.
    """
    seg_q = await db.execute(select(TranscriptSegment).where(TranscriptSegment.call_id == call.id))
    if seg_q.scalars().first() is None:
        return
    h_q = await db.execute(select(Highlight).where(Highlight.call_id == call.id))
    if h_q.scalars().first() is not None:
        return
    try:
        classification = await ClassifierAgent(db).run_post_transcript(call.id, call.caller_number)
        call.is_scam = classification.is_scam
        call.scam_confidence = classification.confidence
        call.scam_type = classification.scam_type
        db.add(call)
        await db.commit()
    except Exception:
        logger.exception("Post-call classification failed; continuing to highlights.")
    await HighlightMinerAgent(db).run(call.id)

async def _transcript_segment_count(db: AsyncSession, call_id: int) -> int:
    r = await db.execute(
        select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.call_id == call_id)
    )
    return int(r.scalar_one() or 0)


_INTRO_ALIASES: dict[str, str] = {
    "Grandma Betty": "Grandma Betty",
    "Parrot (Home Alone Vibe)": "Captain Squawk",
    "Jimmy Fallon": "Midnight Jimmy",
    "Samay Raina": "Chaos Samay",
    "Russell Peters": "Roastmaster Russ",
    "Trevor Noah": "Joburg Trevor",
    "Arnab Goswami": "Arnab",
}


def _opening_greeting(*, persona_key: str, alias: str) -> str:
    """Witty pickup line + ask name/location (ElevenLabs / Twilio first utterance)."""
    if persona_key == "Trevor Noah":
        return (
            f"Hey, it’s {alias}—I’ve got two coffees on the table and I’m ready for a story. "
            f"Who’s this, and where are you calling from?"
        )
    if persona_key == "Arnab Goswami":
        return (
            f"Good evening, you’re live on the debate panel. I’m {alias}. "
            f"State your name and your city—quickly—because the nation is watching. Who are you and where are you calling from?"
        )
    if persona_key == "Parrot (Home Alone Vibe)":
        return (
            f"What’s on your mind, monkey butt? {alias} here—who’s calling, and where are you at?"
        )
    if persona_key == "Grandma Betty":
        return (
            f"Well butter my biscuit—{alias} on the line. Who’s this dear voice, and where are you calling from?"
        )
    if persona_key == "Jimmy Fallon":
        return (
            f"Yo—{alias} here, energy at eleven! Who’s on the phone and what city are you bringing the vibes from?"
        )
    if persona_key == "Samay Raina":
        return (
            f"Arrey—{alias} speaking. Kaun hai tu, aur kahan se phone kiya? …In English: who’s this and where are you calling from?"
        )
    if persona_key == "Russell Peters":
        return (
            f"Alright alright—{alias} here, you’ve got thirty seconds of my curiosity. Who are you and where you calling from?"
        )
    if persona_key == "Miranda Priestly":
        return (
            f"{alias}. You have interrupted something important. Identify yourself and your city—succinctly."
        )
    if persona_key == "Ronny Chieng":
        return (
            f"{alias} here—okay WHO is this and WHERE are you calling from, because this already feels like a lot."
        )
    return (
        f"{alias} speaking—quick, before my toast burns: who’s calling, and where are you calling from?"
    )


def _intake_followup_prompt(persona_key: str | None) -> str:
    """Second prompt after name/location (still TTS, persona-flavored)."""
    if persona_key == "Trevor Noah":
        return "Beautiful—names logged, vibes noted. Now hit me with the plot twist: what’s this call actually about?"
    if persona_key == "Arnab Goswami":
        return "Good—the nation has your coordinates. Now confess plainly: what do you want from me on this line?"
    if persona_key == "Parrot (Home Alone Vibe)":
        return "Roger-dodger, you’re officially on my fridge list. Now dish it—what’s the caper, and how spicy is it?"
    if persona_key == "Grandma Betty":
        return "Well aren’t you polite—my hearing aid’s perked up. Now sugar, what’s the ruckus you’re selling today?"
    if persona_key == "Jimmy Fallon":
        return "Yes! Energy! I’m clapping in my kitchen! Now the cold open—what’s the bit, what do you need from me?"
    if persona_key == "Samay Raina":
        return "Solid intro—main writer credit mil gaya. Ab twist bata: asli kaam kya hai? …What’s the real ask?"
    if persona_key == "Russell Peters":
        return "Alright, you bought a ticket to the show—now earn the laugh. What’s your angle, what do you want?"
    if persona_key == "Miranda Priestly":
        return "That was… adequate. Now skip the throat-clearing—why are you wasting my minutes?"
    if persona_key == "Ronny Chieng":
        return "Cool, I’ve filed you under ‘mystery caller with opinions.’ What’s the actual fire you’re calling about?"
    return "Alright, you’ve got my ear—now make it worth the battery. What’s the main thing you’re calling about?"


async def _build_prompt_twiml(
    *,
    call_sid: str,
    prompt_text: str,
    persona_voice_id: str | None,
    say_voice: str,
    action_path: str,
    initial_wait_seconds: int,
    recording_status_callback: str | None = None,
    start_call_recording: bool = False,
) -> str:
    """
    Use persona ElevenLabs voice for prompts when available, otherwise Twilio <Say>.
    Keeps the opening/intake voice consistent with the persona.
    """
    rec = recording_status_callback if start_call_recording else None
    if persona_voice_id and persona_voice_id.strip():
        host = settings.ngrok_url.removeprefix("https://")
        cache_key = f"{call_sid}_prompt_{abs(hash(prompt_text)) % 1_000_000_000}"
        try:
            mp3_path = await tts_to_mp3_file(text=prompt_text, voice_id=persona_voice_id, cache_key=cache_key)
            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                play_url = f"https://{host}/voice/audio/{cache_key}.mp3"
                return build_gather_twiml(
                    call_sid=call_sid,
                    play_url=play_url,
                    say_voice=say_voice,
                    speech_silence_seconds=0.5,
                    initial_wait_seconds=initial_wait_seconds,
                    action_path=action_path,
                    recording_status_callback=rec,
                )
        except Exception:
            logger.exception("ElevenLabs TTS failed for prompt; falling back to Twilio <Say>.")

    return build_gather_twiml(
        call_sid=call_sid,
        say_text=prompt_text,
        say_voice=say_voice,
        speech_silence_seconds=0.5,
        initial_wait_seconds=initial_wait_seconds,
        action_path=action_path,
        recording_status_callback=rec,
    )


@router.post("/incoming")
async def incoming_call(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio webhook — fires the moment an inbound call connects.

    Pipeline:
      1. Create Call row (scam_type stays unknown until the call ends)
      2. PersonaAgent    → pick persona (locked name or default; not tied to guessed scam type)
      3. Return TwiML (stream or gather+intake)
    """
    form = await request.form()
    call_sid: str = str(form.get("CallSid", "MOCK_SID"))
    caller: str = str(form.get("From", "unknown"))

    # Twilio may retry webhooks; make this idempotent on CallSid.
    existing_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = existing_q.scalar_one_or_none()
    if call is None:
        call = Call(twilio_call_sid=call_sid, caller_number=caller)
        db.add(call)
        await db.commit()
        await db.refresh(call)

    # Keep incoming webhook lightweight to reduce answer latency.
    # Classification can happen after first utterance in /gather.
    if not call.scam_type:
        call.scam_type = "unknown"
    persona_result = await PersonaAgent(db).run(call.id, call.scam_type)
    call.persona_id = persona_result.db_id

    db.add(call)
    await db.commit()

    pub = _public_https_base()
    rec_cb = f"{pub}/voice/recording/status" if pub else None
    do_rec = bool(settings.record_voice_calls and rec_cb)

    if settings.voice_mode.strip().lower() == "stream":
        twiml = build_stream_twiml(
            call_sid,
            recording_status_callback=rec_cb if do_rec else None,
        )
    else:
        alias = _INTRO_ALIASES.get(persona_result.name, persona_result.name or "there")
        greeting = _opening_greeting(persona_key=persona_result.name, alias=alias)
        if await _transcript_segment_count(db, call.id) == 0:
            await persist_segment(
                db,
                call_id=call.id,
                speaker="persona",
                text=greeting,
                timestamp_ms=0,
                confidence=1.0,
            )
        say_voice = twilio_say_voice_for_persona(persona_result.name)
        twiml = await _build_prompt_twiml(
            call_sid=call_sid,
            prompt_text=greeting,
            persona_voice_id=persona_result.elevenlabs_voice_id,
            say_voice=say_voice,
            action_path=f"/voice/intake/{call_sid}",
            initial_wait_seconds=8,
            recording_status_callback=rec_cb,
            start_call_recording=do_rec,
        )
    return Response(content=twiml, media_type="application/xml")


@router.post("/intake/{call_sid}")
async def intake(
    call_sid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    First turn after pickup:
    - STT: caller says who/where they're calling from
    - Persist it
    - Loop into the normal gather endpoint
    """
    stt = await SpeechToTextAgent().run(request)

    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call is None:
        return Response(content=build_gather_twiml(call_sid=call_sid, say_text="Sorry, goodbye."), media_type="application/xml")

    now_ms = int((datetime.utcnow() - call.started_at).total_seconds() * 1000) if call.started_at else 0
    persona_data = None
    if call.persona_id:
        p_q = await db.execute(select(Persona).where(Persona.id == call.persona_id))
        persona_orm = p_q.scalar_one_or_none()
        if persona_orm:
            persona_data = PersonaAgent.orm_to_result(persona_orm)

    if stt.text:
        await persist_segment(
            db,
            call_id=call.id,
            speaker="scammer",
            text=stt.text,
            timestamp_ms=now_ms,
            confidence=stt.confidence,
        )
        prompt = _intake_followup_prompt(persona_data.name if persona_data else None)
    else:
        prompt = "Sorry—my ears did a whole Broadway exit. One more time: who’s calling, and where are you at?"

    await persist_segment(
        db,
        call_id=call.id,
        speaker="persona",
        text=prompt,
        timestamp_ms=now_ms + 50,
        confidence=1.0,
    )

    say_voice = twilio_say_voice_for_persona(persona_data.name if persona_data else None)
    twiml = await _build_prompt_twiml(
        call_sid=call_sid,
        prompt_text=prompt,
        persona_voice_id=(persona_data.elevenlabs_voice_id if persona_data else None),
        say_voice=say_voice,
        action_path=f"/voice/gather/{call_sid}",
        initial_wait_seconds=10,
    )
    return Response(content=twiml, media_type="application/xml")


@router.get("/audio/{cache_key}.mp3")
async def voice_audio(cache_key: str) -> FileResponse:
    """Serve cached ElevenLabs MP3 files to Twilio <Play>."""
    from pathlib import Path

    path = Path(".voice_cache") / f"{cache_key}.mp3"
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


@router.post("/gather/{call_sid}")
async def gather_speech(
    call_sid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Twilio <Gather input="speech"> callback.

    Reads SpeechResult, logs transcript, calls DialogueAgent, then responds with TwiML
    that speaks Betty's line and gathers the next scammer utterance.
    """
    stt = await SpeechToTextAgent().run(request)
    scammer_text = stt.text
    stt_confidence = stt.confidence

    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call is None:
        return Response(content=build_gather_twiml(call_sid=call_sid, say_text="Sorry, goodbye."), media_type="application/xml")

    # Fetch persona
    persona_data = None
    if call.persona_id:
        p_q = await db.execute(select(Persona).where(Persona.id == call.persona_id))
        persona_orm = p_q.scalar_one_or_none()
        if persona_orm:
            persona_data = PersonaAgent.orm_to_result(persona_orm)

    if not scammer_text:
        twiml = build_gather_twiml(
            call_sid=call_sid,
            say_text="I didn't hear anything. Please repeat that.",
            say_voice=twilio_say_voice_for_persona(persona_data.name if persona_data else None),
            speech_silence_seconds=0.5,
            initial_wait_seconds=8,
        )
        return Response(content=twiml, media_type="application/xml")

    now_ms = int((datetime.utcnow() - call.started_at).total_seconds() * 1000) if call.started_at else 0

    # 1) speech to text agent: understands what they're saying (Twilio STT)
    await persist_segment(
        db,
        call_id=call.id,
        speaker="scammer",
        text=scammer_text,
        timestamp_ms=now_ms,
        confidence=stt_confidence,
    )

    if persona_data is None:
        twiml = build_gather_twiml(
            call_sid=call_sid,
            say_text="Oh my stars, something went wrong on my end.",
            say_voice=twilio_say_voice_for_persona(None),
        )
        return Response(content=twiml, media_type="application/xml")

    # Repair-turn strategy: only when audio/STT is genuinely weak — not on short
    # valid replies like "Yeah" / "No" / "OK" (those need a real LLM response).
    word_n = len(scammer_text.split())
    if stt_confidence < 0.22 or (word_n < 2 and stt_confidence < 0.34):
        repair_line = (
            "I caught only part of that. Could you repeat the exact amount and who you are calling from?"
        )
        db.add(TranscriptSegment(
            call_id=call.id,
            speaker="persona",
            text=repair_line,
            timestamp_ms=now_ms + 700,
            is_final=True,
            confidence=1.0,
        ))
        await db.commit()
        twiml = await _build_prompt_twiml(
            call_sid=call_sid,
            prompt_text=repair_line,
            persona_voice_id=persona_data.elevenlabs_voice_id,
            say_voice=twilio_say_voice_for_persona(persona_data.name),
            action_path=f"/voice/gather/{call_sid}",
            initial_wait_seconds=10,
        )
        return Response(content=twiml, media_type="application/xml")

    # Rebuild full transcript history so the persona keeps context across the whole call.
    seg_q = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.call_id == call.id)
        .order_by(TranscriptSegment.id.asc())
    )
    segments = list(seg_q.scalars().all())
    history: list[dict[str, str]] = []
    for s in segments[:-1]:
        role = "user" if s.speaker == "scammer" else "assistant"
        msg = {"role": role, "content": s.text}
        if history and history[-1]["role"] == role:
            history[-1]["content"] = f"{history[-1]['content']}\n\n{s.text}"
        else:
            history.append(msg)

    # LLMs expect the transcript to start with the caller (user) when possible.
    if history and history[0]["role"] == "assistant":
        history.insert(0, {"role": "user", "content": "[Call connected—they’re on the line after my greeting.]"})
    history = normalize_chat_messages(history)

    # 2) response generator: generates a funny response (often a question)
    utterance = await ResponseGenerator(db).run(
        call_id=call.id,
        persona=persona_data,
        history=history,
        scammer_text=scammer_text,
    )

    await persist_segment(
        db,
        call_id=call.id,
        speaker="persona",
        text=utterance,
        timestamp_ms=now_ms + 700,
        confidence=1.0,
    )

    # 3) text to speech: says this response after ~2s silence ends their turn
    twiml = await TextToSpeechAgent().run(
        call_sid=call_sid,
        utterance=utterance,
        voice_id=persona_data.elevenlabs_voice_id,
        persona_name=persona_data.name,
    )
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
                    conversation_history.append(
                        {"role": "assistant", "content": dialogue_result.utterance}
                    )

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
        await _post_call_classify_and_highlights(db, call)


@router.post("/recording/status")
async def recording_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Twilio Recording status callback (<Start><Recording>).
    Persists RecordingSid when processing completes so the app can play audio later.
    """
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    rec_sid = str(form.get("RecordingSid", ""))
    rec_url = str(form.get("RecordingUrl", "")).strip()
    status = str(form.get("RecordingStatus", "")).lower()
    dur_raw = str(form.get("RecordingDuration", "0")).strip()

    if not call_sid or not rec_sid:
        return {"ok": "skip"}

    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call is None:
        logger.warning("Recording callback for unknown CallSid=%s", call_sid)
        return {"ok": "unknown_call"}

    if status == "completed":
        try:
            dur = int(float(dur_raw))
        except ValueError:
            dur = 0
        call.recording_sid = rec_sid
        if rec_url:
            call.recording_url = rec_url
        call.recording_duration_seconds = dur
        db.add(call)
        await db.commit()
        logger.info("Stored recording for call id=%s sid=%s duration=%ss", call.id, rec_sid, dur)

    return {"ok": "true"}


@router.post("/status")
async def call_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Twilio status callback — keeps Call.status in sync with Twilio's truth."""
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    twilio_status = str(form.get("CallStatus", ""))
    duration = int(str(form.get("CallDuration", 0)))

    call_q = await db.execute(select(Call).where(Call.twilio_call_sid == call_sid))
    call = call_q.scalar_one_or_none()
    if call:
        call.status = twilio_status
        call.duration_seconds = duration
        if not call.ended_at:
            call.ended_at = datetime.utcnow()
        db.add(call)
        await db.commit()
        if twilio_status in {"completed", "canceled", "busy", "failed", "no-answer"}:
            await _post_call_classify_and_highlights(db, call)

    return {"ok": True}

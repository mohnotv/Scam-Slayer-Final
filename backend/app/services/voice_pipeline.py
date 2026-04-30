from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.dialogue import DialogueAgent
from backend.app.agents.persona import PersonaResult
from backend.app.config import settings
from backend.app.db.models import TranscriptSegment
from backend.app.services.elevenlabs_tts import tts_to_mp3_file
from backend.app.services.twilio_client import build_gather_twiml, twilio_say_voice_for_persona

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SttResult:
    text: str
    confidence: float


class SpeechToTextAgent:
    """
    Twilio-native STT adapter.

    Twilio posts SpeechResult + Confidence to our webhook.
    """

    async def run(self, request: Request) -> SttResult:
        form = await request.form()
        text = str(form.get("SpeechResult", "")).strip()
        conf_raw = str(form.get("Confidence", "")).strip()
        try:
            conf = float(conf_raw) if conf_raw else 0.0
        except ValueError:
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        return SttResult(text=text, confidence=conf)


class ResponseGenerator:
    """
    Generates the next persona line (question/banter) from transcript context.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        *,
        call_id: int,
        persona: PersonaResult,
        history: list[dict[str, str]],
        scammer_text: str,
    ) -> str:
        agent = DialogueAgent(self._db)
        result = await agent.run(call_id, persona, history, scammer_text)
        return result.utterance


class TextToSpeechAgent:
    """
    Prefer ElevenLabs TTS; fall back to Twilio <Say>.
    Returns TwiML that plays/says the utterance and gathers next speech.
    """

    async def run(
        self,
        *,
        call_sid: str,
        utterance: str,
        voice_id: str | None,
        persona_name: str | None = None,
        say_voice: str | None = None,
    ) -> str:
        say_voice_eff = say_voice or twilio_say_voice_for_persona(persona_name)

        host = settings.ngrok_url.removeprefix("https://")
        cache_key = f"{call_sid}_{abs(hash(utterance)) % 1_000_000_000}"
        if not (voice_id or "").strip():
            return build_gather_twiml(
                call_sid=call_sid,
                say_text=utterance,
                say_voice=say_voice_eff,
                speech_silence_seconds=0.5,
            )
        try:
            mp3_path = await tts_to_mp3_file(text=utterance, voice_id=voice_id, cache_key=cache_key)
            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                play_url = f"https://{host}/voice/audio/{cache_key}.mp3"
                return build_gather_twiml(
                    call_sid=call_sid,
                    play_url=play_url,
                    say_voice=say_voice_eff,
                    speech_silence_seconds=0.5,
                )
        except Exception:
            logger.exception("ElevenLabs TTS failed; falling back to Twilio <Say>.")

        return build_gather_twiml(
            call_sid=call_sid,
            say_text=utterance,
            say_voice=say_voice_eff,
            speech_silence_seconds=0.5,
        )


async def persist_segment(
    db: AsyncSession,
    *,
    call_id: int,
    speaker: str,
    text: str,
    timestamp_ms: int,
    confidence: float = 1.0,
) -> None:
    db.add(TranscriptSegment(
        call_id=call_id,
        speaker=speaker,
        text=text,
        timestamp_ms=timestamp_ms,
        is_final=True,
        confidence=confidence,
    ))
    await db.commit()


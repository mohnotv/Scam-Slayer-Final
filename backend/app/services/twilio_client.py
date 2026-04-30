"""
Twilio client helpers.

Wraps TwiML generation and Twilio REST API calls.
All webhook routing lives in routes/voice.py; this module is pure client logic.
"""

from twilio.twiml.voice_response import VoiceResponse, Connect, Gather, Stream

from backend.app.config import settings


def twilio_say_voice_for_persona(persona_name: str | None) -> str:
    """
    Twilio <Say> only supports built-in voices; we map persona → least-wrong fallback.
    Prefer ElevenLabs <Play> for real persona timbre; this is only when TTS must use <Say>.
    """
    name = (persona_name or "").strip()
    if not name:
        return "alice"
    # Male-leaning personas (generic Twilio "man" is closer than "alice").
    maleish = {
        "Trevor Noah",
        "Arnab Goswami",
        "Ronny Chieng",
        "Russell Peters",
        "Jimmy Fallon",
        "Samay Raina",
    }
    if name in maleish:
        return "man"
    return "alice"


def build_stream_twiml(
    call_sid: str,
    *,
    recording_status_callback: str | None = None,
) -> str:
    """
    Return TwiML that connects the call to our Media Stream WebSocket.
    Twilio will stream bidirectional mulaw 8kHz audio to /voice/stream/{call_sid}.
    """
    response = VoiceResponse()
    if recording_status_callback:
        response.start().recording(
            recording_status_callback=recording_status_callback,
            recording_status_callback_method="POST",
            recording_status_callback_event="completed",
        )
    connect = Connect()
    stream = Stream(
        url=f"wss://{settings.ngrok_url.removeprefix('https://')}/voice/stream/{call_sid}"
    )
    connect.append(stream)
    response.append(connect)
    return str(response)


def build_gather_twiml(
    *,
    call_sid: str,
    say_text: str | None = None,
    play_url: str | None = None,
    say_voice: str = "alice",
    speech_silence_seconds: float = 0.5,
    initial_wait_seconds: int = 6,
    action_path: str | None = None,
    recording_status_callback: str | None = None,
) -> str:
    """
    Return TwiML that uses Twilio speech recognition (no Deepgram required).

    Flow:
      - Optional <Say> prompt
      - <Gather input="speech"> posts SpeechResult to /voice/gather/{call_sid}
      - If no speech, fall back to a reprompt and loop
    """
    host = settings.ngrok_url.removeprefix("https://")
    action = f"https://{host}{action_path}" if action_path else f"https://{host}/voice/gather/{call_sid}"

    response = VoiceResponse()
    if recording_status_callback:
        response.start().recording(
            recording_status_callback=recording_status_callback,
            recording_status_callback_method="POST",
            recording_status_callback_event="completed",
        )
    if play_url:
        response.play(play_url)
    elif say_text:
        response.say(say_text, voice=say_voice)

    # Seconds of silence after speech before Twilio posts SpeechResult (can be fractional in TwiML).
    st = float(speech_silence_seconds)
    if st < 0.2:
        st = 0.2
    if st > 10.0:
        st = 10.0

    gather = Gather(
        input="speech",
        action=action,
        method="POST",
        # End the caller's turn when we detect ~N seconds of silence after speech.
        speech_timeout=st,
        speech_model="phone_call",
        profanity_filter=False,
        # How long to wait for them to start talking at all.
        timeout=max(1, int(initial_wait_seconds)),
        language="en-US",
    )
    response.append(gather)

    # If the caller stays silent, Twilio continues to this part.
    response.say("Sorry, I didn't catch that. Could you say it again?", voice=say_voice)
    response.redirect(action, method="POST")
    return str(response)


def build_reject_twiml(reason: str = "Not a scam call — goodbye.") -> str:
    """Return TwiML that says a message and hangs up (used when classifier says not-scam)."""
    response = VoiceResponse()
    response.say(reason)
    response.hangup()
    return str(response)

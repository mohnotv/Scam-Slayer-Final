"""
Twilio client helpers.

Wraps TwiML generation and Twilio REST API calls.
All webhook routing lives in routes/voice.py; this module is pure client logic.
"""

from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from backend.app.config import settings


def build_stream_twiml(call_sid: str) -> str:
    """
    Return TwiML that connects the call to our Media Stream WebSocket.
    Twilio will stream bidirectional mulaw 8kHz audio to /voice/stream/{call_sid}.
    """
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(
        url=f"wss://{settings.ngrok_url.removeprefix('https://')}/voice/stream/{call_sid}"
    )
    connect.append(stream)
    response.append(connect)
    return str(response)


def build_reject_twiml(reason: str = "Not a scam call — goodbye.") -> str:
    """Return TwiML that says a message and hangs up (used when classifier says not-scam)."""
    response = VoiceResponse()
    response.say(reason)
    response.hangup()
    return str(response)

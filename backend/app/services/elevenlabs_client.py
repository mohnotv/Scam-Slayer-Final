"""
ElevenLabs TTS client.

MVP status: MOCK — `synthesize` returns silent audio bytes.
Next step: call ElevenLabs streaming API with the persona's voice_id.
"""

from backend.app.config import settings


async def synthesize(
    text: str,
    voice_id: str,
    *,
    model_id: str = "eleven_turbo_v2",
) -> bytes:
    """
    Convert text to speech using the specified ElevenLabs voice.

    Args:
        text:     The persona utterance to synthesize.
        voice_id: ElevenLabs voice ID from the Persona row.
        model_id: ElevenLabs model (turbo for low latency on live calls).

    Returns:
        Raw audio bytes (mp3) suitable for streaming back through Twilio.
    """
    # MOCK: return minimal silent MP3 bytes
    return _silent_mp3()


def _silent_mp3() -> bytes:
    """256 bytes of valid (silent) MP3 — just enough to not break decoders."""
    # ID3 header + one silent MPEG frame
    return (
        b"\xff\xfb\x90\x00"  # MPEG1 Layer3 frame header
        + b"\x00" * 252
    )

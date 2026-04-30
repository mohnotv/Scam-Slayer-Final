"""
ElevenLabs TTS helper.

We generate an MP3 file per turn and serve it back to Twilio via <Play>.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)


def _voice_cache_dir() -> Path:
    d = Path(".voice_cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


async def tts_to_mp3_file(*, text: str, voice_id: str, cache_key: str) -> Path:
    """
    Synthesize `text` with ElevenLabs and write an mp3 to a stable cache path.

    Returns the mp3 file path.
    """
    api_key = settings.elevenlabs_api_key
    if not api_key or api_key == "placeholder":
        raise RuntimeError("ELEVENLABS_API_KEY is missing; set it in .env")

    out_path = _voice_cache_dir() / f"{cache_key}.mp3"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": settings.elevenlabs_model_id,
        "voice_settings": {
            "stability": settings.elevenlabs_stability,
            "similarity_boost": settings.elevenlabs_similarity_boost,
            "style": settings.elevenlabs_style,
            "use_speaker_boost": settings.elevenlabs_use_speaker_boost,
        },
    }

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, headers=headers, json=payload)

    if r.status_code >= 400:
        logger.error("ElevenLabs error %s: %s", r.status_code, r.text[:5000])
        raise RuntimeError(f"ElevenLabs API error {r.status_code}: {r.text[:500]}")

    out_path.write_bytes(r.content)
    return out_path


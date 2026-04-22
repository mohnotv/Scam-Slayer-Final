"""
Deepgram STT client.

MVP status: MOCK — `transcribe_stream` yields fixture transcript chunks.
Next step: open a real Deepgram Nova-3 WebSocket and pipe mulaw audio frames.
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass
class TranscriptChunk:
    text: str
    is_final: bool
    timestamp_ms: int
    confidence: float


async def transcribe_stream(
    audio_stream: AsyncGenerator[bytes, None],
) -> AsyncGenerator[TranscriptChunk, None]:
    """
    Stream audio bytes to Deepgram and yield transcript chunks as they arrive.

    Args:
        audio_stream: Async generator of raw mulaw 8kHz audio bytes from Twilio.

    Yields:
        TranscriptChunk with partial and final transcription results.
    """
    async for _ in audio_stream:
        # MOCK: consume audio and yield fixture chunks.
        # `yield from` is invalid in async generators — iterate explicitly.
        for chunk in _mock_chunks():
            yield chunk
        return  # one pass only for mock


def _mock_chunks() -> list[TranscriptChunk]:
    """Fixture transcript simulating a short IRS scam call."""
    return [
        TranscriptChunk(
            "Hello, this is the IRS.",
            is_final=True,
            timestamp_ms=1200,
            confidence=0.98,
        ),
        TranscriptChunk(
            "You owe back taxes.",
            is_final=True,
            timestamp_ms=3400,
            confidence=0.97,
        ),
        TranscriptChunk(
            "You must pay immediately or face arrest.",
            is_final=True,
            timestamp_ms=6100,
            confidence=0.95,
        ),
    ]

"""
Classifier Agent

Inputs:
    call_id       — DB id of the already-created Call row
    caller_number — raw caller-ID string from Twilio (e.g. "+15005550006")
    audio_bytes   — optional first-10s audio segment (mulaw 8 kHz); None if not yet available

Outputs:
    ClassifierResult — is_scam, confidence (0–1), scam_type label

Side effects:
    Writes one AgentEvent row to the DB with the classification payload.

``run()`` (caller-ID triage): mock path returns a fixed IRS label when the LLM fails.

``run_post_transcript()``: preferred for production — classifies from the full transcript after
the call; falls back to keyword heuristics when the LLM fails.
"""

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, TranscriptSegment
from backend.app.services.llm_client import generate_text
from backend.app.services.runtime_settings import get_active_llm_provider


class ClassifierResult(BaseModel):
    """Typed output of the Classifier Agent."""

    is_scam: bool
    confidence: float = Field(ge=0.0, le=1.0)
    scam_type: str  # e.g. "irs_impersonation" | "tech_support" | "grandparent" | "lottery"


class ClassifierAgent:
    """
    Decides whether an incoming call is a scam and categorises the scam type.

    Instantiate per-request and call ``await agent.run(...)``.
    """

    # Fixed mock result matching the Phase 3 spec exactly.
    _MOCK = ClassifierResult(is_scam=True, confidence=0.87, scam_type="irs_impersonation")

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        call_id: int,
        caller_number: str,
        audio_bytes: bytes | None = None,
    ) -> ClassifierResult:
        """
        Run classification on an incoming call.

        Returns ClassifierResult and persists an AgentEvent for dashboard replay.
        """
        # Try Gemini-backed classification (fallback to mock).
        try:
            result = await self._run_llm(caller_number=caller_number)
            mocked = False
        except Exception:
            result = self._run_mock(caller_number, audio_bytes)
            mocked = True

        await self._emit_classification_event(
            call_id=call_id,
            result=result,
            caller_number=caller_number,
            mocked=mocked,
            extra={"audio_provided": audio_bytes is not None, "phase": "caller_id"},
        )
        return result

    async def _emit_classification_event(
        self,
        call_id: int,
        result: ClassifierResult,
        *,
        caller_number: str,
        mocked: bool,
        extra: dict | None = None,
    ) -> None:
        payload: dict = {
            "is_scam": result.is_scam,
            "confidence": result.confidence,
            "scam_type": result.scam_type,
            "caller_number": caller_number,
            "mocked": mocked,
        }
        if extra:
            payload.update(extra)
        self._db.add(AgentEvent(
            call_id=call_id,
            agent="classifier",
            event_type="classification_complete",
            payload=payload,
        ))
        await self._db.commit()

    async def run_post_transcript(self, call_id: int, caller_number: str) -> ClassifierResult:
        """
        Classify using the full transcript after the call (or simulate) has content.

        Used instead of pre-briefing the persona with a guessed scam type from caller ID alone.
        """
        seg_q = await self._db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.call_id == call_id)
            .order_by(TranscriptSegment.id)
        )
        segments = seg_q.scalars().all()
        lines: list[str] = []
        for s in segments:
            label = "CALLER" if s.speaker == "scammer" else "PERSONA"
            lines.append(f"{label}: {s.text}")
        transcript = "\n".join(lines).strip()

        if not transcript:
            result = ClassifierResult(is_scam=False, confidence=0.0, scam_type="unknown")
            await self._emit_classification_event(
                call_id=call_id,
                result=result,
                caller_number=caller_number,
                mocked=True,
                extra={"phase": "post_transcript", "note": "empty_transcript"},
            )
            return result

        clipped = transcript if len(transcript) <= 14_000 else transcript[:14_000] + "\n…[truncated]"
        try:
            result = await self._run_llm_from_transcript(
                transcript=clipped,
                caller_number=caller_number,
            )
            mocked = False
        except Exception:
            result = self._run_mock_from_transcript(transcript)
            mocked = True

        await self._emit_classification_event(
            call_id=call_id,
            result=result,
            caller_number=caller_number,
            mocked=mocked,
            extra={"phase": "post_transcript"},
        )
        return result

    @staticmethod
    def _run_mock(caller_number: str, audio_bytes: bytes | None) -> ClassifierResult:
        """
        MOCK: always returns a high-confidence IRS scam regardless of input.
        Replace this method body with real model inference when ready.
        """
        return ClassifierResult(is_scam=True, confidence=0.87, scam_type="irs_impersonation")

    async def _run_llm(self, *, caller_number: str) -> ClassifierResult:
        """
        LLM: lightweight scam-type classifier based on context we have at call start.
        (Caller ID only is weak, so this is best-effort with fallback.)
        """
        system = (
            "You are a call triage classifier for an anti-scam system.\n"
            "Return JSON only with keys: is_scam (bool), confidence (0-1), scam_type (string).\n"
            "Allowed scam_type values: irs_impersonation, tech_support, grandparent, lottery, medicare, unknown."
        )
        user = f"Caller number: {caller_number}\nClassify the call intent. If unsure, use scam_type='unknown' with low confidence."
        provider = await get_active_llm_provider(self._db)
        text = await generate_text(
            provider=provider,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=120,
        )
        # Minimal tolerant parse.
        import json

        data = json.loads(text)
        return ClassifierResult(
            is_scam=bool(data.get("is_scam", True)),
            confidence=float(data.get("confidence", 0.3)),
            scam_type=str(data.get("scam_type", "unknown")),
        )

    async def _run_llm_from_transcript(self, *, transcript: str, caller_number: str) -> ClassifierResult:
        system = (
            "You are reviewing a phone-call transcript between a bait persona (PERSONA) and a caller (CALLER).\n"
            "Decide whether the CALLER is running a scam or social-engineering fraud.\n"
            "Return JSON only with keys: is_scam (bool), confidence (0-1), scam_type (string).\n"
            "Allowed scam_type values: irs_impersonation, tech_support, grandparent, lottery, medicare, unknown."
        )
        user = (
            f"Caller ID (weak signal): {caller_number}\n\n"
            f"Transcript:\n{transcript}\n\n"
            "Classify mainly from what the CALLER said. If unclear, use scam_type='unknown' with lower confidence."
        )
        provider = await get_active_llm_provider(self._db)
        text = await generate_text(
            provider=provider,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=180,
        )
        import json

        data = json.loads(text)
        return ClassifierResult(
            is_scam=bool(data.get("is_scam", True)),
            confidence=float(data.get("confidence", 0.3)),
            scam_type=str(data.get("scam_type", "unknown")),
        )

    @staticmethod
    def _run_mock_from_transcript(transcript: str) -> ClassifierResult:
        """Heuristic fallback when the transcript LLM path fails (no API keys, parse errors, etc.)."""
        low = transcript.lower()
        if any(k in low for k in ["irs", "tax warrant", "back taxes", "owe tax", "federal tax"]):
            return ClassifierResult(is_scam=True, confidence=0.82, scam_type="irs_impersonation")
        if any(k in low for k in ["gift card", "google play", "virus on your computer", "remote desktop", "microsoft"]):
            return ClassifierResult(is_scam=True, confidence=0.78, scam_type="tech_support")
        if any(k in low for k in ["grandson", "grandchild", "your grandson", "in jail", "bail"]):
            return ClassifierResult(is_scam=True, confidence=0.75, scam_type="grandparent")
        if any(k in low for k in ["lottery", "prize", "winner", "sweepstakes"]):
            return ClassifierResult(is_scam=True, confidence=0.72, scam_type="lottery")
        if "medicare" in low:
            return ClassifierResult(is_scam=True, confidence=0.74, scam_type="medicare")
        if any(k in low for k in ["ssn", "social security", "wire", "bitcoin", "urgent payment"]):
            return ClassifierResult(is_scam=True, confidence=0.55, scam_type="unknown")
        return ClassifierResult(is_scam=False, confidence=0.35, scam_type="unknown")

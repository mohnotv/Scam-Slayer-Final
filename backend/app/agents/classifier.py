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

Mock status: ALWAYS returns is_scam=True, confidence=0.87, scam_type="irs_impersonation".
Next step: replace _run_mock() with TeleAntiFraud-28k model inference
           (see analysis/01_scam_classifier_teleantifraud.ipynb).
"""

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent


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
        result = self._run_mock(caller_number, audio_bytes)

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="classifier",
            event_type="classification_complete",
            payload={
                "is_scam": result.is_scam,
                "confidence": result.confidence,
                "scam_type": result.scam_type,
                "caller_number": caller_number,
                "audio_provided": audio_bytes is not None,
                "mocked": True,
            },
        ))
        await self._db.commit()

        return result

    @staticmethod
    def _run_mock(caller_number: str, audio_bytes: bytes | None) -> ClassifierResult:
        """
        MOCK: always returns a high-confidence IRS scam regardless of input.
        Replace this method body with real model inference when ready.
        """
        return ClassifierResult(is_scam=True, confidence=0.87, scam_type="irs_impersonation")

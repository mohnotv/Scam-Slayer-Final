"""
Classifier Agent

Inputs:  caller metadata (phone number, call SID) + optional first-10s audio bytes
Outputs: ClassifierResult(is_scam, confidence, scam_type)
Side effects: logs an AgentEvent to the DB

MVP status: MOCK — returns hardcoded high-confidence scam result.
Next step: replace `_classify_mock` with the TeleAntiFraud-28k fine-tuned model
           (see analysis/01_scam_classifier_teleantifraud.ipynb).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent


@dataclass
class ClassifierResult:
    is_scam: bool
    confidence: float  # 0.0 – 1.0
    scam_type: str  # e.g. "irs_impersonation", "tech_support", "grandparent"


async def classify_call(
    call_id: int,
    caller_number: str,
    db: AsyncSession,
    audio_bytes: bytes | None = None,
) -> ClassifierResult:
    """
    Run the classifier on an incoming call.

    Args:
        call_id:       DB id of the Call row (already created).
        caller_number: Raw caller-ID string from Twilio.
        db:            Async DB session for logging.
        audio_bytes:   Optional first-10s audio segment (mulaw 8kHz).

    Returns:
        ClassifierResult with scam verdict, confidence, and type label.
    """
    result = _classify_mock(caller_number, audio_bytes)

    event = AgentEvent(
        call_id=call_id,
        agent="classifier",
        event_type="classification_complete",
        payload={
            "is_scam": result.is_scam,
            "confidence": result.confidence,
            "scam_type": result.scam_type,
            "caller_number": caller_number,
            "audio_provided": audio_bytes is not None,
        },
    )
    db.add(event)
    await db.commit()

    return result


def _classify_mock(caller_number: str, audio_bytes: bytes | None) -> ClassifierResult:
    """
    MOCK implementation — always returns a high-confidence IRS scam.
    Replace this with real model inference when the classifier is ready.
    """
    return ClassifierResult(
        is_scam=True,
        confidence=0.95,
        scam_type="irs_impersonation",
    )

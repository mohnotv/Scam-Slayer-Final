"""
Coach chat API.

Lets users ask "why did the agent respond this way?" questions about a call.
"""

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException

from backend.app.db.models import AgentEvent, Call, TranscriptSegment
from backend.app.db.session import get_db
from backend.app.services.llm_client import generate_text
from backend.app.config import settings

router = APIRouter(prefix="/coach", tags=["coach"])


class CoachChatRequest(BaseModel):
    call_id: int
    question: str = Field(min_length=2, max_length=500)
    focus_segment_id: int | None = None


class CoachChatResponse(BaseModel):
    answer: str
    used_llm: bool


@router.post("/chat", response_model=CoachChatResponse)
async def coach_chat(body: CoachChatRequest, db: AsyncSession = Depends(get_db)) -> CoachChatResponse:
    call_q = await db.execute(select(Call).where(Call.id == body.call_id))
    call = call_q.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    focus_segment: TranscriptSegment | None = None
    if body.focus_segment_id is not None:
        f_q = await db.execute(
            select(TranscriptSegment).where(
                TranscriptSegment.call_id == body.call_id,
                TranscriptSegment.id == body.focus_segment_id,
            )
        )
        focus_segment = f_q.scalar_one_or_none()

    if focus_segment is not None:
        # Narrow context around the focused line
        seg_q = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.call_id == body.call_id)
            .order_by(TranscriptSegment.timestamp_ms, TranscriptSegment.id)
        )
        all_segments = seg_q.scalars().all()
        idx = next((i for i, s in enumerate(all_segments) if s.id == focus_segment.id), 0)
        lo = max(0, idx - 6)
        hi = min(len(all_segments), idx + 7)
        segments = all_segments[lo:hi]
    else:
        seg_q = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.call_id == body.call_id)
            .order_by(TranscriptSegment.timestamp_ms, TranscriptSegment.id)
            .limit(60)
        )
        segments = seg_q.scalars().all()

    ev_q = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.call_id == body.call_id)
        .order_by(AgentEvent.created_at.desc())
        .limit(20)
    )
    events = list(reversed(ev_q.scalars().all()))

    transcript_text = "\n".join([f"{s.speaker}: {s.text}" for s in segments])[:9000]
    events_text = "\n".join([f"{e.agent}/{e.event_type}: {e.payload}" for e in events])[:5000]

    system = (
        "You are a call-analysis assistant for ScamSlayer.\n"
        "Explain why the AI agent responded the way it did, grounded in transcript and events.\n"
        "Be concise, factual, and mention uncertainty when needed."
    )
    parts: list[str] = [
        f"Call meta: id={call.id}, persona_id={call.persona_id}, status={call.status}",
        "",
    ]
    if focus_segment is not None:
        parts.extend([
            f"Focused segment: speaker={focus_segment.speaker}, text={focus_segment.text}",
            "",
        ])
    parts.extend([
        "Transcript:",
        transcript_text,
        "",
        "Agent events:",
        events_text,
        "",
        f"User question: {body.question}",
    ])
    user = "\n".join(parts)

    try:
        answer = await generate_text(
            provider=settings.llm_provider,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=220,
        )
        answer = answer.strip() or "I could not infer a reliable reason from the current transcript."
        return CoachChatResponse(answer=answer, used_llm=True)
    except Exception:
        # deterministic fallback when API keys/models are unavailable
        fallback = (
            "Based on the transcript, the agent tends to prioritize stalling and clarification. "
            "It likely responded that way because it detected scam cues and followed persona rules "
            "(short replies, confusion prompts, and keeping the caller talking)."
        )
        return CoachChatResponse(answer=fallback, used_llm=False)


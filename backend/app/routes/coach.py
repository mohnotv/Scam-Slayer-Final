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
from backend.app.services.runtime_settings import (
    get_active_llm_provider,
    get_dialogue_preferences,
    set_dialogue_preferences,
)

router = APIRouter(prefix="/coach", tags=["coach"])

class CoachMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class CoachChatRequest(BaseModel):
    call_id: int
    question: str = Field(min_length=2, max_length=500)
    focus_segment_id: int | None = None
    history: list[CoachMessage] = []


class CoachChatResponse(BaseModel):
    answer: str
    used_llm: bool


class CoachPrefsOut(BaseModel):
    dialogue_goal: str
    humor_level: str


class CoachPrefsIn(BaseModel):
    dialogue_goal: str = Field(pattern="^(engage|clarify)$")
    humor_level: str = Field(pattern="^(high|medium|low|off)$")


@router.get("/preferences", response_model=CoachPrefsOut)
async def get_prefs(db: AsyncSession = Depends(get_db)) -> CoachPrefsOut:
    prefs = await get_dialogue_preferences(db)
    return CoachPrefsOut(dialogue_goal=prefs["dialogue_goal"], humor_level=prefs["humor_level"])


@router.put("/preferences", response_model=CoachPrefsOut)
async def set_prefs(body: CoachPrefsIn, db: AsyncSession = Depends(get_db)) -> CoachPrefsOut:
    try:
        prefs = await set_dialogue_preferences(
            db,
            dialogue_goal=body.dialogue_goal,
            humor_level=body.humor_level,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CoachPrefsOut(dialogue_goal=prefs["dialogue_goal"], humor_level=prefs["humor_level"])


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
        "You are ScamSlayer Coach, an interactive chat assistant.\n"
        "You can answer general questions, but when asked about a call you must ground answers in the provided transcript and agent events.\n"
        "Be concise, factual, and mention uncertainty when needed."
    )
    context_parts: list[str] = [
        f"Call meta: id={call.id}, persona_id={call.persona_id}, status={call.status}",
        "",
    ]
    prefs = await get_dialogue_preferences(db)
    context_parts.extend([
        f"Current dialogue preferences: goal={prefs['dialogue_goal']}, humor={prefs['humor_level']}",
        "",
    ])
    if focus_segment is not None:
        context_parts.extend([
            f"Focused segment: speaker={focus_segment.speaker}, text={focus_segment.text}",
            "",
        ])
    context_parts.extend([
        "Transcript:",
        transcript_text,
        "",
        "Agent events:",
        events_text,
        "",
        "If the user asks about the call, use the above context. If they ask a general question, answer normally.",
    ])
    context = "\n".join(context_parts)

    # Convert UI chat history into LLM messages; keep it bounded.
    messages: list[dict[str, str]] = [{"role": "user", "content": context}]
    for m in (body.history or [])[-24:]:
        r = (m.role or "").strip().lower()
        if r not in {"user", "assistant"}:
            continue
        c = (m.content or "").strip()
        if not c:
            continue
        messages.append({"role": r, "content": c})
    # Append the latest question as the final user turn.
    messages.append({"role": "user", "content": body.question})

    try:
        provider = await get_active_llm_provider(db)
        answer = await generate_text(
            provider=provider,
            system=system,
            messages=messages,
            max_tokens=500,
        )
        answer = answer.strip() or "I could not infer a reliable reason from the current transcript."
        return CoachChatResponse(answer=answer, used_llm=True)
    except Exception:
        # deterministic fallback when API keys/models are unavailable
        fallback = (
            "I can’t reach the LLM right now, but I can still help. "
            "If you paste the exact persona line you’re asking about, I’ll point to the most likely trigger in the transcript "
            "(e.g., gift cards, threats, remote access, urgency) and what the agent was trying to get the scammer to say next."
        )
        return CoachChatResponse(answer=fallback, used_llm=False)


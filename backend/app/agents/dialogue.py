"""
Dialogue Agent

Inputs:  Persona, running transcript text, conversation history
Outputs: Next persona utterance (string)
Side effects: streams response from Claude API; logs AgentEvent

MVP status: PARTIAL — Claude API is wired and called for real.
            STT input and TTS output are still mocked (see services/).
Next step: pipe real Deepgram transcript chunks here; stream ElevenLabs TTS back.
"""

import json

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.models import AgentEvent, Persona

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_system_prompt(persona: Persona) -> str:
    return f"""You are roleplaying as {persona.name} for an anti-scam baiting operation.
Your goal is to keep the scammer on the line as long as possible while staying in character.

PERSONA
-------
{persona.backstory}

SPEECH STYLE
------------
{persona.speech_tics}

RULES
-----
- Never break character, no matter what the scammer says.
- Never give real financial information. Invent plausible-sounding but fake details.
- Keep responses short (1-3 sentences) to maintain a natural phone-call rhythm.
- Introduce small confusions and digressions to stall (ask them to repeat, mention Mr. Whiskers, etc.).
- Do NOT reveal you are an AI or part of any experiment.
- If directly accused of being a bot, respond with confused elderly indignation.
"""


async def generate_response(
    call_id: int,
    persona: Persona,
    conversation_history: list[dict],
    latest_scammer_text: str,
    db: AsyncSession,
) -> str:
    """
    Generate the next persona utterance via Claude.

    Args:
        call_id:                DB id of the active Call.
        persona:                The active Persona ORM instance.
        conversation_history:   List of {"role": "user"|"assistant", "content": str} dicts.
        latest_scammer_text:    Most recent transcribed scammer turn.
        db:                     Async DB session for event logging.

    Returns:
        The persona's next spoken line as a plain string.
    """
    messages = conversation_history + [{"role": "user", "content": latest_scammer_text}]

    response_text = await _call_claude(persona, messages)

    event = AgentEvent(
        call_id=call_id,
        agent="dialogue",
        event_type="utterance_generated",
        payload={
            "scammer_input": latest_scammer_text,
            "persona_response": response_text,
            "turn_index": len(conversation_history) // 2,
        },
    )
    db.add(event)
    await db.commit()

    return response_text


async def _call_claude(persona: Persona, messages: list[dict]) -> str:
    """Call Claude API and return the full response text."""
    client = _get_client()
    message = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=256,
        system=_build_system_prompt(persona),
        messages=messages,
    )
    content = message.content[0]
    if content.type == "text":
        return content.text
    return ""

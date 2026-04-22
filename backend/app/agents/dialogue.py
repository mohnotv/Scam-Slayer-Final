"""
Dialogue Agent

Inputs:
    call_id      — DB id of the active Call
    persona      — PersonaResult from the Persona Agent
    history      — list of {"role": "user"|"assistant", "content": str} dicts (running conversation)
    scammer_text — most recent transcribed scammer utterance (from Deepgram or mock)

Outputs:
    DialogueResult — utterance (string to speak), turn_index, mocked flag

Side effects:
    Writes one AgentEvent row with the scammer input and persona response.

Toggle:
    MOCK_CLAUDE=true (default) — returns a canned Grandma Betty response from
        backend/app/agents/fixtures/betty_responses.json, cycling by turn index.
    MOCK_CLAUDE=false — calls the real Claude API (claude-sonnet-4-5) with the
        full persona system prompt. Requires ANTHROPIC_API_KEY to be set.

Next step: pipe real Deepgram transcript chunks here as scammer_text;
           stream ElevenLabs TTS on the utterance back through Twilio.
"""

import json
import logging
from pathlib import Path
from typing import cast

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.persona import PersonaResult
from backend.app.config import settings
from backend.app.db.models import AgentEvent

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "betty_responses.json"

# Lazy singleton — only created when MOCK_CLAUDE=false
_claude_client: AsyncAnthropic | None = None


def _get_claude_client() -> AsyncAnthropic:
    global _claude_client
    if _claude_client is None:
        _claude_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _claude_client


class DialogueResult(BaseModel):
    """Typed output of the Dialogue Agent."""

    utterance: str   # the persona's spoken response — pass to TTS
    turn_index: int  # 0-based turn count within this call
    mocked: bool     # True when MOCK_CLAUDE=true


class DialogueAgent:
    """
    Generates the next persona utterance given the scammer's latest speech.

    Instantiate per-request (or per-call) and call ``await agent.run(...)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._fixture: list[str] | None = None

    async def run(
        self,
        call_id: int,
        persona: PersonaResult,
        history: list[dict[str, str]],
        scammer_text: str,
    ) -> DialogueResult:
        """
        Generate the next spoken line for the persona.

        Args:
            call_id:      DB id of the active Call.
            persona:      Persona data from PersonaAgent.run().
            history:      Previous turns as {"role": ..., "content": ...} dicts.
                          Must alternate user/assistant, starting with user.
            scammer_text: Latest final transcript from the scammer's side.

        Returns:
            DialogueResult with the utterance to synthesise via TTS.
        """
        turn_index = len(history) // 2

        if settings.mock_claude:
            utterance = self._mock_response(turn_index)
            mocked = True
            logger.debug("DialogueAgent [mock] turn=%d: %s", turn_index, utterance[:60])
        else:
            utterance = await self._call_claude(persona, history, scammer_text)
            mocked = False
            logger.debug("DialogueAgent [claude] turn=%d: %s", turn_index, utterance[:60])

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="dialogue",
            event_type="utterance_generated",
            payload={
                "scammer_input": scammer_text,
                "persona_response": utterance,
                "turn_index": turn_index,
                "mocked": mocked,
            },
        ))
        await self._db.commit()

        return DialogueResult(utterance=utterance, turn_index=turn_index, mocked=mocked)

    # ── Mock path ──────────────────────────────────────────────────────────────

    def _mock_response(self, turn_index: int) -> str:
        """Return a canned Betty response, cycling through the fixture list."""
        if self._fixture is None:
            self._fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        return self._fixture[turn_index % len(self._fixture)]

    # ── Real Claude path ───────────────────────────────────────────────────────

    @staticmethod
    def _build_system_prompt(persona: PersonaResult) -> str:
        return f"""You are roleplaying as {persona.name} for an anti-scam baiting operation.
Your goal is to keep the scammer on the line as long as possible while staying in character.

PERSONA (age {persona.age})
-------
{persona.backstory}

SPEECH STYLE
------------
{persona.speech_tics}

RULES
-----
- Never break character, no matter what the scammer says.
- Never give real financial information. Invent plausible-sounding but fake details.
- Keep responses short (1–3 sentences) to maintain a natural phone-call rhythm.
- Introduce small confusions and digressions to stall (ask them to repeat,
  look for your glasses, mention Mr. Whiskers, reference your cookies, etc.).
- Do NOT reveal you are an AI or part of any experiment.
- If directly accused of being a bot, respond with confused elderly indignation.
"""

    async def _call_claude(
        self,
        persona: PersonaResult,
        history: list[dict[str, str]],
        scammer_text: str,
    ) -> str:
        """Call the real Claude API and return the response text."""
        client = _get_claude_client()
        raw_messages = list(history) + [{"role": "user", "content": scammer_text}]
        # The SDK types MessageParam more narrowly than dict[str,str]; cast is safe
        # because the structure is identical — role + content strings.
        messages = cast(list[MessageParam], raw_messages)
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=256,
            system=self._build_system_prompt(persona),
            messages=messages,
        )
        block = response.content[0]
        return block.text if block.type == "text" else ""

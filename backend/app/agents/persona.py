"""
Persona Agent

Inputs:
    call_id      — DB id of the active Call
    scam_type    — label from ClassifierResult (e.g. "irs_impersonation")
    persona_name — optional override; if None, the agent picks the best match

Outputs:
    PersonaResult — all persona data needed by downstream agents (Dialogue, Editor)

Side effects:
    May INSERT a new Persona row if Betty doesn't exist yet.
    Writes one AgentEvent row.

Mock status: always returns Grandma Betty (age 78, retired teacher, chatty,
             hard of hearing, loves cookies and her cat Mr. Whiskers).
Next step: use Claude to generate novel personas tailored to the detected scam type;
           pull voice IDs from the ElevenLabs voice catalogue dynamically.
"""

import json

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Persona


class PersonaResult(BaseModel):
    """Typed output of the Persona Agent — everything downstream agents need."""

    db_id: int
    name: str
    age: int
    backstory: str
    speech_tics: str
    elevenlabs_voice_id: str
    scam_types: list[str]


# ── Grandma Betty definition ──────────────────────────────────────────────────

_BETTY_NAME = "Grandma Betty"
_BETTY_AGE = 78

_BETTY_DB_FIELDS: dict[str, str] = {
    "name": _BETTY_NAME,
    "backstory": (
        "Betty Mae Henderson, 78, retired schoolteacher from Tulsa, Oklahoma. "
        "Widowed four years ago. Dotes on her six grandchildren. "
        "Bakes cookies every Sunday — famous for her snickerdoodles and pecan pie. "
        "Hard of hearing in her left ear; asks callers to repeat themselves constantly. "
        "Genuinely sweet and trusting but gets confused by anything technical or rushed. "
        "Tends to ramble: digresses mid-sentence into stories about her cat Mr. Whiskers, "
        "her son-in-law Gerald, and her church bingo group. "
        "Deeply suspicious of anything that feels pressured, but too polite to say so outright."
    ),
    "speech_tics": (
        "Exclaims 'Oh my stars!' when surprised. "
        "Calls everyone 'honey' or 'dear'. "
        "Loses her train of thought mid-sentence and says 'Now where was I?'. "
        "Mentions Mr. Whiskers at least once per conversation unprompted. "
        "Frequently needs to find her reading glasses before doing anything. "
        "References her cookies / baking when stalling. "
        "Brings up her grandson Bobby when asked about technology."
    ),
    "elevenlabs_voice_id": "EXAVITQu4vr4xnSDxMaL",  # 'Bella' — warm elderly female
    "scam_types": json.dumps(
        ["irs_impersonation", "grandparent", "lottery", "tech_support", "medicare"]
    ),
}


class PersonaAgent:
    """
    Selects or creates the appropriate AI persona for the scam type.

    Instantiate per-request and call ``await agent.run(...)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        call_id: int,
        scam_type: str,
        persona_name: str | None = None,
    ) -> PersonaResult:
        """
        Choose a persona and persist it if new.

        Returns PersonaResult with db_id so the caller can set Call.persona_id.
        """
        persona_orm = await self._get_or_create_betty()
        result = self._to_result(persona_orm)

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="persona",
            event_type="persona_selected",
            payload={
                "persona_name": result.name,
                "persona_db_id": result.db_id,
                "scam_type": scam_type,
                "mocked": True,
            },
        ))
        await self._db.commit()

        return result

    async def _get_or_create_betty(self) -> Persona:
        """Fetch Grandma Betty from DB or insert her if she doesn't exist yet."""
        q = await self._db.execute(select(Persona).where(Persona.name == _BETTY_NAME))
        existing = q.scalar_one_or_none()
        if existing is not None:
            return existing

        betty = Persona(**_BETTY_DB_FIELDS)
        self._db.add(betty)
        await self._db.commit()
        await self._db.refresh(betty)
        return betty

    @staticmethod
    def _to_result(persona: Persona) -> PersonaResult:
        return PersonaResult(
            db_id=persona.id,
            name=persona.name,
            age=_BETTY_AGE,
            backstory=persona.backstory,
            speech_tics=persona.speech_tics,
            elevenlabs_voice_id=persona.elevenlabs_voice_id,
            scam_types=json.loads(persona.scam_types),
        )

    @staticmethod
    def orm_to_result(persona: Persona) -> PersonaResult:
        """
        Convert an already-fetched Persona ORM row to PersonaResult.
        Used by the WebSocket handler to reconstruct context mid-call.
        """
        return PersonaAgent._to_result(persona)

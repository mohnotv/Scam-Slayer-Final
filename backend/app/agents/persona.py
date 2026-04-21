"""
Persona Agent

Inputs:  scam_type string, optional explicit persona name
Outputs: Persona DB row (fetched or newly created)
Side effects: may INSERT a new Persona row; logs AgentEvent

MVP status: MOCK — always returns static "Grandma Betty" persona,
            creating it in the DB on first use.
Next step: use Claude to generate novel personas tailored to the scam type;
           pull voice IDs from ElevenLabs catalogue.
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Persona

GRANDMA_BETTY: dict = {
    "name": "Grandma Betty",
    "backstory": (
        "Betty Mae Henderson, 78, retired schoolteacher from Tulsa, Oklahoma. "
        "Widowed 4 years ago. Dotes on her 6 grandchildren. Tends to ramble about "
        "her famous pecan pie recipe and her cat, Mr. Whiskers. Hard of hearing — "
        "asks callers to repeat themselves. Gets confused by tech terms. "
        "Genuinely sweet but deeply suspicious of anything that feels rushed."
    ),
    "speech_tics": (
        "Says 'Oh my stars!' when surprised. Calls everyone 'honey' or 'dear'. "
        "Frequently loses track of sentences mid-thought. Mentions Mr. Whiskers unprompted."
    ),
    "elevenlabs_voice_id": "EXAVITQu4vr4xnSDxMaL",  # 'Bella' — warm elderly female
    "scam_types": json.dumps(["irs_impersonation", "grandparent", "lottery", "tech_support"]),
}


async def select_persona(
    call_id: int,
    scam_type: str,
    db: AsyncSession,
    persona_name: str | None = None,
) -> Persona:
    """
    Choose a persona appropriate for the detected scam type.

    Args:
        call_id:      DB id of the active Call.
        scam_type:    Label from ClassifierResult (e.g. "irs_impersonation").
        db:           Async DB session.
        persona_name: Optional override — force a specific persona by name.

    Returns:
        A Persona ORM instance (persisted in DB).
    """
    persona = await _select_mock(db, persona_name)

    event = AgentEvent(
        call_id=call_id,
        agent="persona",
        event_type="persona_selected",
        payload={"persona_name": persona.name, "scam_type": scam_type},
    )
    db.add(event)
    await db.commit()

    return persona


async def _select_mock(db: AsyncSession, persona_name: str | None) -> Persona:
    """
    MOCK: Always returns Grandma Betty, creating her if she doesn't exist yet.
    """
    target_name = persona_name or GRANDMA_BETTY["name"]
    result = await db.execute(select(Persona).where(Persona.name == target_name))
    persona = result.scalar_one_or_none()

    if persona is None:
        data = GRANDMA_BETTY if target_name == GRANDMA_BETTY["name"] else GRANDMA_BETTY
        persona = Persona(**data)
        db.add(persona)
        await db.commit()
        await db.refresh(persona)

    return persona

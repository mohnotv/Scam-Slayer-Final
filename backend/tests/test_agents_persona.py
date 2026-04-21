"""
Persona Agent tests.
"""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.persona import PersonaAgent, PersonaResult
from backend.app.db.models import AgentEvent, Call, Persona


@pytest.mark.asyncio
async def test_run_returns_persona_result(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert isinstance(result, PersonaResult)


@pytest.mark.asyncio
async def test_returns_grandma_betty(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert result.name == "Grandma Betty"


@pytest.mark.asyncio
async def test_betty_age_is_78(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert result.age == 78


@pytest.mark.asyncio
async def test_betty_backstory_mentions_teacher(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert "teacher" in result.backstory.lower() or "schoolteacher" in result.backstory.lower()


@pytest.mark.asyncio
async def test_betty_backstory_mentions_hard_of_hearing(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert "hearing" in result.backstory.lower()


@pytest.mark.asyncio
async def test_betty_speech_tics_mention_cookies(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert "cookie" in result.speech_tics.lower() or "bak" in result.speech_tics.lower()


@pytest.mark.asyncio
async def test_betty_has_voice_id(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert len(result.elevenlabs_voice_id) > 0


@pytest.mark.asyncio
async def test_betty_scam_types_include_irs(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert "irs_impersonation" in result.scam_types


@pytest.mark.asyncio
async def test_db_id_is_set(db: AsyncSession, call: Call) -> None:
    result = await PersonaAgent(db).run(call.id, "irs_impersonation")
    assert result.db_id is not None and result.db_id > 0


@pytest.mark.asyncio
async def test_idempotent_no_duplicates(db: AsyncSession, call: Call) -> None:
    """Two calls should not insert duplicate Persona rows."""
    await PersonaAgent(db).run(call.id, "irs_impersonation")
    await PersonaAgent(db).run(call.id, "tech_support")

    q = await db.execute(select(Persona))
    assert len(q.scalars().all()) == 1


@pytest.mark.asyncio
async def test_persists_agent_event(db: AsyncSession, call: Call) -> None:
    await PersonaAgent(db).run(call.id, "grandparent")

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "persona",
        )
    )
    event = q.scalar_one()
    assert event.event_type == "persona_selected"
    assert event.payload["persona_name"] == "Grandma Betty"
    assert event.payload["scam_type"] == "grandparent"


@pytest.mark.asyncio
async def test_orm_to_result_roundtrip(db: AsyncSession, call: Call) -> None:
    """PersonaAgent.orm_to_result should produce the same PersonaResult as .run()."""
    run_result = await PersonaAgent(db).run(call.id, "irs_impersonation")

    orm_q = await db.execute(select(Persona).where(Persona.id == run_result.db_id))
    persona_orm = orm_q.scalar_one()
    reconstructed = PersonaAgent.orm_to_result(persona_orm)

    assert reconstructed.name == run_result.name
    assert reconstructed.backstory == run_result.backstory
    assert reconstructed.db_id == run_result.db_id

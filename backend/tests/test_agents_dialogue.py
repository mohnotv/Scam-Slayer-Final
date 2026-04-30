"""
Dialogue Agent tests.

All tests use MOCK_CLAUDE=true (the default) so no API key is needed.
The hosted-LLM path is covered by a patch test that verifies the dispatch logic.
"""

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.dialogue import DialogueAgent, DialogueResult
from backend.app.agents.persona import PersonaAgent, PersonaResult
from backend.app.db.models import AgentEvent, Call


# ── Shared fixture: persona result ────────────────────────────────────────────

@pytest.fixture
async def persona(db: AsyncSession, call: Call) -> PersonaResult:
    return await PersonaAgent(db).run(call.id, "irs_impersonation")


# ── Basic output contract ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_returns_dialogue_result(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    result = await DialogueAgent(db).run(call.id, persona, [], "Hello, you owe taxes.")
    assert isinstance(result, DialogueResult)


@pytest.mark.asyncio
async def test_utterance_is_nonempty(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    result = await DialogueAgent(db).run(call.id, persona, [], "Pay now or be arrested.")
    assert len(result.utterance.strip()) > 0


@pytest.mark.asyncio
async def test_mocked_flag_true_by_default(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    with patch("backend.app.agents.dialogue.settings") as mock_settings:
        mock_settings.mock_claude = True
        result = await DialogueAgent(db).run(call.id, persona, [], "Hello.")
    assert result.mocked is True


@pytest.mark.asyncio
async def test_turn_index_zero_on_first_call(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    result = await DialogueAgent(db).run(call.id, persona, [], "First scammer line.")
    assert result.turn_index == 0


@pytest.mark.asyncio
async def test_turn_index_increments_with_history(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    history: list[dict[str, str]] = [
        {"role": "user", "content": "Turn 0 scammer"},
        {"role": "assistant", "content": "Turn 0 betty"},
        {"role": "user", "content": "Turn 1 scammer"},
        {"role": "assistant", "content": "Turn 1 betty"},
    ]
    result = await DialogueAgent(db).run(call.id, persona, history, "Turn 2 scammer")
    assert result.turn_index == 2


# ── Fixture cycling ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_responses_cycle_across_turns(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    """After exhausting the fixture list, responses should cycle back to index 0."""
    import json
    from pathlib import Path

    fixture_path = Path(__file__).parent.parent / "app/agents/fixtures/betty_responses.json"
    fixture = json.loads(fixture_path.read_text())
    n = len(fixture)

    # Build n turns of history
    history: list[dict[str, str]] = []
    for _ in range(n):
        history.append({"role": "user", "content": "scammer"})
        history.append({"role": "assistant", "content": "betty"})

    # Turn n should wrap around to fixture[0]
    with patch("backend.app.agents.dialogue.settings") as mock_settings:
        mock_settings.mock_claude = True
        result_n = await DialogueAgent(db).run(call.id, persona, history, "scammer again")
    assert result_n.utterance == fixture[0]


# ── Mock toggle → dispatches to Claude path ───────────────────────────────────

@pytest.mark.asyncio
async def test_mock_false_calls_llm(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    """When mock_claude=False, DialogueAgent should call the hosted LLM."""
    fake_response = "Oh my stars, honey, I need to find my glasses first."

    with patch("backend.app.agents.dialogue.settings") as mock_settings, \
         patch.object(DialogueAgent, "_call_llm", new_callable=AsyncMock) as mock_llm:
        mock_settings.mock_claude = False
        mock_settings.llm_provider = "gemini"
        mock_llm.return_value = fake_response

        result = await DialogueAgent(db).run(call.id, persona, [], "Pay now!")

    mock_llm.assert_called_once()
    assert result.utterance == fake_response
    assert result.mocked is False


# ── System prompt sanity ──────────────────────────────────────────────────────

def test_system_prompt_contains_persona_name(db: AsyncSession) -> None:  # type: ignore[misc]
    dummy_persona = PersonaResult(
        db_id=1,
        name="Grandma Betty",
        age=78,
        backstory="Retired teacher.",
        speech_tics="Says oh my stars.",
        elevenlabs_voice_id="test",
        scam_types=[],
    )
    prompt = DialogueAgent._build_system_prompt(dummy_persona)
    assert "Grandma Betty" in prompt
    assert "78" in prompt
    assert "Retired teacher." in prompt
    assert "Never break character" in prompt


# ── DB logging ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persists_agent_event(
    db: AsyncSession, call: Call, persona: PersonaResult
) -> None:
    from sqlalchemy import select

    scammer_text = "You must pay immediately."
    await DialogueAgent(db).run(call.id, persona, [], scammer_text)

    q = await db.execute(
        select(AgentEvent).where(
            AgentEvent.call_id == call.id,
            AgentEvent.agent == "dialogue",
        )
    )
    event = q.scalar_one()
    assert event.event_type == "utterance_generated"
    assert event.payload["scammer_input"] == scammer_text
    assert len(event.payload["persona_response"]) > 0
    assert event.payload["turn_index"] == 0

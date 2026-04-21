"""
Cross-agent smoke tests — run the full mock pipeline end-to-end.
Individual agent behaviour is tested in test_agents_*.py files.
All tests use the shared in-memory DB fixtures from conftest.py.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Call


@pytest.mark.asyncio
async def test_full_pipeline_mock(db: AsyncSession, call: Call) -> None:
    """
    Run all six agents in sequence against the same call.
    Verifies that each agent returns its typed output and doesn't crash.
    """
    from backend.app.agents.classifier import ClassifierAgent
    from backend.app.agents.dialogue import DialogueAgent
    from backend.app.agents.editor import EditorAgent
    from backend.app.agents.highlights import HighlightMinerAgent
    from backend.app.agents.persona import PersonaAgent
    from backend.app.agents.social import SocialAgent

    # 1 — Classifier
    classification = await ClassifierAgent(db).run(call.id, "+15005550006")
    assert classification.is_scam

    # 2 — Persona
    persona = await PersonaAgent(db).run(call.id, classification.scam_type)
    assert persona.db_id is not None
    assert persona.name == "Grandma Betty"

    # 3 — Dialogue (mock path)
    dialogue = await DialogueAgent(db).run(
        call.id, persona, [], "You owe back taxes!"
    )
    assert len(dialogue.utterance) > 0
    assert dialogue.mocked is True

    # 4 — Highlights
    highlights = await HighlightMinerAgent(db).run(call.id)
    assert len(highlights.highlights) >= 2

    # 5 — Editor (writes stub file)
    editor = await EditorAgent(db).run(call.id, highlights, audio_path=None)
    assert editor.db_id is not None
    assert editor.status in ("ready", "stub")

    # 6 — Social
    social = await SocialAgent(db).run(
        call_id=call.id,
        clip_db_id=editor.db_id,
        clip_duration_seconds=editor.duration_seconds,
        call_duration_seconds=call.duration_seconds,
        highlights=highlights,
    )
    assert len(social.caption) > 0
    assert len(social.hashtags) >= 5

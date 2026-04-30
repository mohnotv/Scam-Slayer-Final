"""
Cross-agent smoke tests — run the full mock pipeline end-to-end.
Individual agent behaviour is tested in test_agents_*.py files.
All tests use the shared in-memory DB fixtures from conftest.py.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Call, TranscriptSegment


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

    # 1 — Persona (no pre-call scam triage from caller ID)
    persona = await PersonaAgent(db).run(call.id, "unknown")
    assert persona.db_id is not None
    assert persona.name == "Grandma Betty"

    # 2 — Seed transcript + post-call classification (mirrors voice pipeline)
    db.add(
        TranscriptSegment(
            call_id=call.id,
            speaker="scammer",
            text="This is the IRS, you owe back taxes and must pay today.",
            timestamp_ms=0,
            is_final=True,
            confidence=1.0,
        )
    )
    db.add(
        TranscriptSegment(
            call_id=call.id,
            speaker="persona",
            text="Oh my stars, which IRS office is this again?",
            timestamp_ms=1_000,
            is_final=True,
            confidence=1.0,
        )
    )
    await db.commit()
    classification = await ClassifierAgent(db).run_post_transcript(call.id, "+15005550006")
    assert classification.is_scam

    # 3 — Dialogue (may use mock or hosted LLM depending on env)
    dialogue = await DialogueAgent(db).run(
        call.id, persona, [], "You owe back taxes!"
    )
    assert len(dialogue.utterance) > 0

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

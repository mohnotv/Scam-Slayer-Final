"""
Smoke tests — verify each agent returns without crashing using mock implementations.
Runs without any external API credentials (Anthropic, Twilio, Deepgram, ElevenLabs).

DB fixtures come from conftest.py.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Call


# ── Classifier ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classifier_returns_result(db: AsyncSession, call: Call) -> None:
    from backend.app.agents.classifier import classify_call

    result = await classify_call(call.id, "+15005550006", db)

    assert result.is_scam is True
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.scam_type, str) and result.scam_type


# ── Persona ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persona_returns_grandma_betty(db: AsyncSession, call: Call) -> None:
    from backend.app.agents.persona import select_persona

    persona = await select_persona(call.id, "irs_impersonation", db)

    assert persona.id is not None
    assert persona.name == "Grandma Betty"


@pytest.mark.asyncio
async def test_persona_is_idempotent(db: AsyncSession, call: Call) -> None:
    """Calling select_persona twice should not create duplicate rows."""
    from backend.app.agents.persona import select_persona
    from sqlalchemy import func, select
    from backend.app.db.models import Persona

    await select_persona(call.id, "irs_impersonation", db)
    await select_persona(call.id, "irs_impersonation", db)

    count_result = await db.execute(select(func.count()).select_from(Persona))
    assert count_result.scalar_one() == 1


# ── Highlights ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_highlights_returns_mock_data(db: AsyncSession, call: Call) -> None:
    from backend.app.agents.highlights import mine_highlights

    highlights = await mine_highlights(call.id, db)

    assert len(highlights) >= 1
    for h in highlights:
        assert h.start_ms < h.end_ms
        assert 0.0 <= h.score <= 1.0
        assert isinstance(h.transcript_snippet, str)


# ── Social ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_social_returns_package(db: AsyncSession, call: Call) -> None:
    from backend.app.agents.social import generate_social_package
    from backend.app.db.models import Clip, Highlight

    clip = Clip(call_id=call.id, status="pending")
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    h = Highlight(
        call_id=call.id, start_ms=0, end_ms=10_000, score=0.9, transcript_snippet="test"
    )
    db.add(h)
    await db.commit()

    pkg = await generate_social_package(call.id, clip, call, [h], db)

    assert isinstance(pkg.caption, str) and len(pkg.caption) > 0
    assert isinstance(pkg.hashtags, list) and len(pkg.hashtags) > 0
    assert isinstance(pkg.suggested_post_time, str)

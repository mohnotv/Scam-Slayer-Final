"""
Smoke tests — verify each agent returns without crashing against the mock implementations.
These run without any external API credentials.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.models import Base, Call, Persona
from backend.app.db.session import init_db


# ── In-memory SQLite DB for tests ─────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def call(db: AsyncSession) -> Call:
    c = Call(twilio_call_sid="TEST_SID_001", caller_number="+15005550006")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


# ── Classifier ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classifier_mock(db: AsyncSession, call: Call):
    from backend.app.agents.classifier import classify_call

    result = await classify_call(call.id, "+15005550006", db)
    assert result.is_scam is True
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.scam_type, str)


# ── Persona ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persona_mock(db: AsyncSession, call: Call):
    from backend.app.agents.persona import select_persona

    persona = await select_persona(call.id, "irs_impersonation", db)
    assert persona.id is not None
    assert persona.name == "Grandma Betty"


# ── Highlights ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_highlights_mock(db: AsyncSession, call: Call):
    from backend.app.agents.highlights import mine_highlights

    highlights = await mine_highlights(call.id, db)
    assert len(highlights) >= 1
    for h in highlights:
        assert h.start_ms < h.end_ms
        assert 0.0 <= h.score <= 1.0


# ── Social ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_social_mock(db: AsyncSession, call: Call):
    from backend.app.agents.social import generate_social_package
    from backend.app.db.models import Clip, Highlight

    clip = Clip(call_id=call.id, status="pending")
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    h = Highlight(call_id=call.id, start_ms=0, end_ms=10000, score=0.9, transcript_snippet="test")
    db.add(h)
    await db.commit()

    pkg = await generate_social_package(call.id, clip, call, [h], db)
    assert isinstance(pkg.caption, str) and len(pkg.caption) > 0
    assert isinstance(pkg.hashtags, list) and len(pkg.hashtags) > 0

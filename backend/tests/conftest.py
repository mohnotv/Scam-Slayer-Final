"""
Shared pytest fixtures for the ScamSlayer test suite.

Every test that needs a DB gets a fresh in-memory SQLite database isolated
to that test function.  StaticPool ensures all sessions/connections share
the exact same in-memory database — critical for integration tests where the
HTTP client and the assertion queries must see each other's commits.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.models import Base, Call


# ── Per-test in-memory engine ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_engine():
    """
    Async engine backed by an in-memory SQLite database.

    StaticPool reuses the same connection for every session so all
    sessions see the same tables and committed rows — essential when
    the HTTP client and the assertion queries share one in-memory DB.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine):
    """Open a single AsyncSession for the duration of one unit test."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def call(db: AsyncSession) -> Call:
    """A persisted Call row for tests that need a pre-existing call."""
    c = Call(twilio_call_sid="TEST_SID_001", caller_number="+15005550006")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


# ── HTTP integration-test client ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_engine):
    """
    AsyncClient wired to the FastAPI app, with:
      - get_db dependency overridden to use the per-test in-memory DB
      - init_db / close_db_engine patched out (tables already created by db_engine)
    """
    from backend.app.db.session import get_db
    from backend.app.main import app

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    with (
        patch("backend.app.db.session.init_db", new_callable=AsyncMock),
        patch("backend.app.db.session.close_db_engine", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()

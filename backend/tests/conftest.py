"""
Shared pytest fixtures for the ScamSlayer test suite.

Every test that needs a DB session gets a fresh in-memory SQLite database
isolated to that test function.  No real files are written during the test run.
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.models import Base, Call

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    """
    Per-test async engine against an in-memory SQLite DB.
    Tables are created on entry and dropped on exit.
    """
    engine = create_async_engine(_TEST_DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine):
    """Open a single AsyncSession for the duration of one test."""
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

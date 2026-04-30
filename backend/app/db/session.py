"""
Async SQLAlchemy engine and session factory.

Public API:
  init_db()          — create all tables (called at startup)
  close_db_engine()  — dispose engine (called at shutdown)
  get_db()           — FastAPI dependency, yields an AsyncSession per request
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import settings
from backend.app.db.models import Base

# SQLite needs check_same_thread=False even through the async driver because
# aiosqlite internally uses a worker thread.
_connect_args = (
    {"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _ensure_calls_recording_columns(sync_conn) -> None:
    """SQLite: add recording columns to existing `calls` tables (create_all does not alter)."""
    r = sync_conn.execute(text("PRAGMA table_info(calls)"))
    cols = {row[1] for row in r.fetchall()}
    if "recording_sid" not in cols:
        sync_conn.execute(text("ALTER TABLE calls ADD COLUMN recording_sid VARCHAR(100)"))
    if "recording_url" not in cols:
        sync_conn.execute(text("ALTER TABLE calls ADD COLUMN recording_url TEXT"))
    if "recording_duration_seconds" not in cols:
        sync_conn.execute(text("ALTER TABLE calls ADD COLUMN recording_duration_seconds INTEGER DEFAULT 0"))


async def init_db() -> None:
    """Create all tables if they don't already exist. No Alembic yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if "sqlite" in settings.database_url:
            await conn.run_sync(_ensure_calls_recording_columns)


async def close_db_engine() -> None:
    """Dispose the connection pool — called at application shutdown."""
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session and always closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session

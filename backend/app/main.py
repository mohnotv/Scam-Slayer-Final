"""
ScamSlayer FastAPI entrypoint.

Startup: initialises the SQLite database (create tables if missing, no Alembic yet).
Mounts: /voice (Twilio webhooks + WS), /calls, /personas, /clips.
Dev: run with `uvicorn backend.app.main:app --reload --port 8000`
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.db.session import close_db_engine, init_db
from backend.app.routes import calls, clips, personas, voice

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown side-effects."""
    logger.info("Starting ScamSlayer — initialising database…")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down — closing DB engine.")
    await close_db_engine()


app = FastAPI(
    title="ScamSlayer API",
    description="AI-powered scam-baiter backend.",
    version="0.1.0",
    lifespan=lifespan,
    debug=settings.debug,
)

# Allow the Vite dev server and, in production, the deployed frontend origin.
_cors_origins = ["http://localhost:5173"]
if settings.ngrok_url and "placeholder" not in settings.ngrok_url:
    _cors_origins.append(settings.ngrok_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice.router)
app.include_router(calls.router)
app.include_router(personas.router)
app.include_router(clips.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 as long as the process is up."""
    return {"status": "ok", "service": "scamslayer"}

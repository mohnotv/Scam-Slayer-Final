"""
ScamSlayer FastAPI entrypoint.

Startup: initialises the SQLite database.
Mounts: /voice (Twilio webhooks + WS), /calls, /personas, /clips.
Dev: run with `uvicorn backend.app.main:app --reload --port 8000`
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.session import init_db
from backend.app.routes import calls, clips, personas, voice

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="ScamSlayer API",
    description="AI-powered scam-baiter backend.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


app.include_router(voice.router)
app.include_router(calls.router)
app.include_router(personas.router)
app.include_router(clips.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "scamslayer"}

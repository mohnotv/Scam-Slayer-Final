"""
Application configuration — loaded once at import time from environment variables.
All secrets must live in .env only. Never hardcode values here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = "sk-ant-placeholder"
    anthropic_model: str = "claude-sonnet-4-5"

    # ── Twilio ─────────────────────────────────────────────────────────────────
    twilio_account_sid: str = "ACplaceholder"
    twilio_auth_token: str = "placeholder"

    # ── Deepgram ───────────────────────────────────────────────────────────────
    deepgram_api_key: str = "placeholder"

    # ── ElevenLabs ─────────────────────────────────────────────────────────────
    elevenlabs_api_key: str = "placeholder"

    # ── Persistence ────────────────────────────────────────────────────────────
    # SQLite for dev; swap to postgresql+asyncpg://... for prod
    database_url: str = "sqlite+aiosqlite:///./scamslayer.db"

    # ── Queue ──────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Networking ─────────────────────────────────────────────────────────────
    # Public HTTPS URL from `ngrok http 8000` — used for Twilio webhook config
    ngrok_url: str = "https://placeholder.ngrok-free.app"

    # ── Safety ─────────────────────────────────────────────────────────────────
    # Hard cap on call duration; call is hung up after this many seconds
    max_call_duration_seconds: int = 300

    # ── Application ────────────────────────────────────────────────────────────
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    debug: bool = False      # enables FastAPI debug mode + SQLAlchemy echo


settings = Settings()

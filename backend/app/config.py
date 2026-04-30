"""
Application configuration — loaded once at import time from environment variables.
All secrets must live in .env only. Never hardcode values here.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Resolve relative to repo root (not process cwd) to avoid surprises when
        # uvicorn is started from a different working directory.
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM provider ───────────────────────────────────────────────────────────
    # Which hosted LLM to use when MOCK_CLAUDE=false.
    # Supported: "anthropic" | "gemini"
    llm_provider: str = "anthropic"

    # ── Anthropic ──────────────────────────────────────────────────────────────
    anthropic_api_key: str = "sk-ant-placeholder"
    anthropic_model: str = "claude-sonnet-4-5"

    # ── Gemini ────────────────────────────────────────────────────────────────
    # Uses Google Gemini Generative Language API (REST).
    gemini_api_key: str = "placeholder"
    # Recommended "best quality" default.
    # Example: gemini-2.5-pro-latest
    gemini_model: str = "gemini-2.5-pro-latest"

    # ── ElevenLabs voice tuning ────────────────────────────────────────────────
    elevenlabs_model_id: str = "eleven_turbo_v2_5"
    elevenlabs_stability: float = 0.35
    elevenlabs_similarity_boost: float = 0.85
    elevenlabs_style: float = 0.35
    elevenlabs_use_speaker_boost: bool = True

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

    # ── Voice mode ─────────────────────────────────────────────────────────────
    # "gather": Twilio <Gather input="speech"> (no Deepgram required)
    # "stream": Twilio Media Streams WebSocket (Deepgram integration TODO)
    voice_mode: str = "gather"

    # When true, Twilio records the full call audio (requires recording status webhook URL).
    record_voice_calls: bool = True

    # ── Safety ─────────────────────────────────────────────────────────────────
    # Hard cap on call duration; call is hung up after this many seconds
    max_call_duration_seconds: int = 300

    # ── Application ────────────────────────────────────────────────────────────
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    debug: bool = False      # enables FastAPI debug mode + SQLAlchemy echo

    # ── Agent toggles ──────────────────────────────────────────────────────────
    # Set MOCK_CLAUDE=false to use the configured hosted LLM (LLM_PROVIDER).
    # True by default so the system runs without any API key during development.
    mock_claude: bool = True

    # Max chat messages (user+assistant) sent to the dialogue LLM per turn.
    # Set high so long calls keep full context; lower if you need smaller API payloads.
    dialogue_max_history_messages: int = 4000

    # Max output tokens requested from the hosted LLM per turn.
    # Providers require a finite limit; set this very high to effectively remove the cap.
    # (The dialogue prompt still asks for 1–3 sentences, and we still post-process for phone cadence.)
    dialogue_max_output_tokens: int = 2048

    # Max characters allowed in the final spoken utterance after post-processing.
    # Increased from the old 520 so we don't chop sentences when the model runs long.
    dialogue_max_utterance_chars: int = 900


settings = Settings()

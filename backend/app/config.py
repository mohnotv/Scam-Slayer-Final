"""
Application configuration loaded from environment variables via pydantic-settings.
All secrets must live in .env — never hardcode them here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic
    anthropic_api_key: str = "sk-ant-placeholder"
    anthropic_model: str = "claude-sonnet-4-5"

    # Twilio
    twilio_account_sid: str = "ACplaceholder"
    twilio_auth_token: str = "placeholder"

    # Deepgram
    deepgram_api_key: str = "placeholder"

    # ElevenLabs
    elevenlabs_api_key: str = "placeholder"

    # Database
    database_url: str = "sqlite+aiosqlite:///./scamslayer.db"

    # Redis / arq
    redis_url: str = "redis://localhost:6379/0"

    # ngrok public URL (set after `ngrok http 8000`)
    ngrok_url: str = "https://placeholder.ngrok-free.app"

    # Safety guard — max call duration in seconds
    max_call_duration_seconds: int = 300


settings = Settings()

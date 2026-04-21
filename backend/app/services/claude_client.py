"""
Anthropic Claude client singleton.

Thin wrapper so every agent imports from one place and the API key
is loaded exactly once. Heavy lifting (prompt construction, parsing)
stays in each agent module.
"""

from anthropic import AsyncAnthropic

from backend.app.config import settings

_client: AsyncAnthropic | None = None


def get_claude() -> AsyncAnthropic:
    """Return the shared AsyncAnthropic client (lazy-initialised)."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client

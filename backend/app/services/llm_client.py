"""
LLM client wrapper.

Today only the Dialogue Agent calls a hosted LLM. We keep the integration here
so agent code doesn't depend on any single vendor SDK.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, TypedDict

import httpx

from backend.app.config import settings

logger = logging.getLogger(__name__)
_resolved_gemini_model: str | None = None
_gemini_generate_candidates: list[str] | None = None


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


async def generate_text(
    *,
    provider: str,
    system: str,
    messages: list[ChatMessage],
    max_tokens: int = 256,
) -> str:
    """
    Generate a single text completion from the configured provider.

    Args:
        provider: "anthropic" or "gemini"
        system: system prompt / instruction
        messages: chat history (user/assistant)
        max_tokens: maximum output tokens (provider-specific mapping)
    """
    provider_norm = provider.strip().lower()
    if provider_norm == "anthropic":
        return await _anthropic_generate(system=system, messages=messages, max_tokens=max_tokens)
    if provider_norm == "gemini":
        return await _gemini_generate(system=system, messages=messages, max_tokens=max_tokens)
    raise ValueError(f"Unsupported LLM provider: {provider!r} (expected 'anthropic'|'gemini')")


async def _anthropic_generate(*, system: str, messages: list[ChatMessage], max_tokens: int) -> str:
    # Imported lazily so the rest of the app doesn't depend on Anthropic unless used.
    from anthropic import AsyncAnthropic  # type: ignore[import-not-found]
    from anthropic.types import MessageParam  # type: ignore[import-not-found]

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=list(messages),  # shape matches MessageParam
    )
    block = response.content[0]
    return block.text if getattr(block, "type", None) == "text" else ""


async def _gemini_generate(*, system: str, messages: list[ChatMessage], max_tokens: int) -> str:
    """
    Call Gemini REST API via Generative Language endpoint.

    Docs: https://ai.google.dev/api/rest/v1beta/models/generateContent
    """
    api_key = settings.gemini_api_key
    # Pick a model that actually works for THIS API key (some models 404 depending on access).
    model = await _resolve_working_gemini_model(settings.gemini_model, api_key=api_key, system=system, messages=messages)

    if not api_key or api_key == "placeholder":
        raise RuntimeError("GEMINI_API_KEY is missing; set it in .env (GEMINI_API_KEY=...)")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def _to_gemini_contents(msgs: list[ChatMessage]) -> list[dict]:
        contents: list[dict] = []
        for m in msgs:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        return contents

    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _to_gemini_contents(messages),
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.85,
        },
    }

    timeout = httpx.Timeout(connect=8.0, read=30.0, write=8.0, pool=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)

    if r.status_code >= 400:
        logger.error("Gemini error %s: %s", r.status_code, r.text[:5000])
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:500]}")

    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (((candidates[0].get("content") or {}).get("parts")) or [])
    if not parts:
        return ""
    text = parts[0].get("text")
    return text if isinstance(text, str) else ""


async def _list_gemini_generate_models(*, api_key: str) -> list[str]:
    global _gemini_generate_candidates
    if _gemini_generate_candidates is not None:
        return _gemini_generate_candidates
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    models = data.get("models") or []
    candidates: list[str] = []
    for m in models:
        name = m.get("name")
        methods = m.get("supportedGenerationMethods") or []
        if not isinstance(name, str):
            continue
        if "generateContent" not in methods:
            continue
        if "/gemini" not in name:
            continue
        short = name.removeprefix("models/")
        # Avoid non-text / special-purpose models in phone-call chat.
        low = short.lower()
        if any(bad in low for bad in ["-image", "vision", "embedding", "computer-use", "tts", "speech"]):
            continue
        candidates.append(short)
    _gemini_generate_candidates = candidates
    return candidates


async def _resolve_working_gemini_model(
    desired_model: str,
    *,
    api_key: str,
    system: str,
    messages: list[ChatMessage],
) -> str:
    """
    Pick a model that supports generateContent AND is actually callable with this API key.
    Some models appear in ListModels but still 404 for certain users/projects.
    """
    global _resolved_gemini_model
    if _resolved_gemini_model:
        return _resolved_gemini_model

    desired = (desired_model or "").strip()
    candidates = await _list_gemini_generate_models(api_key=api_key)
    if not candidates:
        _resolved_gemini_model = "gemini-1.5-flash"
        return _resolved_gemini_model

    ordered: list[str] = []
    if desired and desired.lower() != "latest" and desired in candidates:
        ordered.append(desired)

    preferred = [
        "gemini-1.5-pro-latest",
        "gemini-1.5-pro",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
    ]
    for p in preferred:
        if p in candidates and p not in ordered:
            ordered.append(p)

    for c in sorted(candidates):
        if c not in ordered:
            ordered.append(c)

    # Probe a few models until one works.
    probe_payload = {
        "systemInstruction": {"parts": [{"text": system[:400]}]},
        "contents": [{"role": "user", "parts": [{"text": (messages[-1]["content"] if messages else "Hi")[:400]}]}],
        "generationConfig": {"maxOutputTokens": 8, "temperature": 0.2},
    }
    timeout = httpx.Timeout(connect=8.0, read=15.0, write=8.0, pool=8.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for m in ordered[:8]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            try:
                r = await client.post(url, json=probe_payload)
            except Exception:  # noqa: BLE001
                continue
            if r.status_code < 400:
                _resolved_gemini_model = m
                return _resolved_gemini_model
            # For 404/permission-ish errors, try next model.
            if r.status_code in {403, 404}:
                continue

    # If none worked, fall back to the first candidate and let the real call raise a useful error.
    _resolved_gemini_model = ordered[0]
    return _resolved_gemini_model


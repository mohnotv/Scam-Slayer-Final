"""
Service checks API.

Used by the frontend "Checks" tab to verify external dependencies are reachable:
- Gemini (Generative Language API)
- ElevenLabs (voices + TTS)
- Twilio (account auth)
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.config import settings
import backend.app.services.llm_client as llm_client
import asyncio

router = APIRouter(prefix="/checks", tags=["checks"])


class CheckResult(BaseModel):
    ok: bool
    latency_ms: int
    detail: str | None = None


class ChecksOut(BaseModel):
    gemini: CheckResult
    anthropic: CheckResult
    elevenlabs: CheckResult
    twilio: CheckResult


async def _timed(fn, *, timeout_s: float = 8.0):
    t0 = time.perf_counter()
    try:
        detail = await asyncio.wait_for(fn(), timeout=timeout_s)
        ms = int((time.perf_counter() - t0) * 1000)
        return CheckResult(ok=True, latency_ms=ms, detail=detail)
    except Exception as e:  # noqa: BLE001
        ms = int((time.perf_counter() - t0) * 1000)
        # asyncio.TimeoutError stringifies to "" by default; make it explicit.
        detail = str(e) or e.__class__.__name__
        return CheckResult(ok=False, latency_ms=ms, detail=detail)


@router.get("", response_model=ChecksOut)
async def get_checks() -> ChecksOut:
    async def _check_gemini() -> str:
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key or api_key == "placeholder":
            raise RuntimeError("GEMINI_API_KEY missing")
        # Fast direct probe against the configured model (avoid slow model-listing/resolver).
        model = (settings.gemini_model or "").strip()
        if not model:
            raise RuntimeError("GEMINI_MODEL missing")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": "Reply with exactly the word pong."}]},
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": 16, "temperature": 0.0},
        }
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini {r.status_code}: {(r.text or '')[:200]}")
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            raise RuntimeError("Gemini returned non-JSON response")
        txt = llm_client._extract_gemini_response_text(data)  # reuse parser
        if not (txt or "").strip():
            c0 = (data.get("candidates") or [{}])[0]
            raise RuntimeError(f"Gemini empty text (finishReason={c0.get('finishReason')})")
        return f"model={model}"

    async def _check_anthropic() -> str:
        api_key = (settings.anthropic_api_key or "").strip()
        if not api_key or api_key.startswith("sk-ant-placeholder"):
            raise RuntimeError("ANTHROPIC_API_KEY missing")
        # Use the Anthropic SDK path already used by the app.
        out = await llm_client.generate_text(
            provider="anthropic",
            system="Health check. Reply with exactly the word pong.",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=16,
        )
        if not (out or "").strip():
            raise RuntimeError("Anthropic returned empty text")
        return f"model={settings.anthropic_model}"

    async def _check_elevenlabs() -> str:
        api_key = (settings.elevenlabs_api_key or "").strip()
        if not api_key or api_key == "placeholder":
            raise RuntimeError("ELEVENLABS_API_KEY missing")
        # Voices endpoint is a quick auth check.
        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": api_key, "accept": "application/json"}
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs {r.status_code}: {(r.text or '')[:200]}")
        return f"model_id={settings.elevenlabs_model_id}"

    async def _check_twilio() -> str:
        sid = (settings.twilio_account_sid or "").strip()
        tok = (settings.twilio_auth_token or "").strip()
        if not sid or sid == "ACplaceholder":
            raise RuntimeError("TWILIO_ACCOUNT_SID missing")
        if not tok or tok == "placeholder":
            raise RuntimeError("TWILIO_AUTH_TOKEN missing")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
        timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, auth=(sid, tok), headers={"accept": "application/json"})
        if r.status_code >= 400:
            raise RuntimeError(f"Twilio {r.status_code}: {(r.text or '')[:200]}")
        return f"account={sid}"

    return ChecksOut(
        gemini=await _timed(_check_gemini),
        anthropic=await _timed(_check_anthropic),
        elevenlabs=await _timed(_check_elevenlabs),
        twilio=await _timed(_check_twilio),
    )


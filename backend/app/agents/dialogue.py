"""
Dialogue Agent

Inputs:
    call_id      — DB id of the active Call
    persona      — PersonaResult from the Persona Agent
    history      — list of {"role": "user"|"assistant", "content": str} dicts (running conversation)
    scammer_text — most recent transcribed scammer utterance (from Deepgram or mock)

Outputs:
    DialogueResult — utterance (string to speak), turn_index, mocked flag

Side effects:
    Writes one AgentEvent row with the scammer input and persona response.

Toggle:
    MOCK_CLAUDE=true (default) — returns a canned Grandma Betty response from
        backend/app/agents/fixtures/betty_responses.json, cycling by turn index.
    MOCK_CLAUDE=false — calls the configured hosted LLM (LLM_PROVIDER) with the
        full persona system prompt. Requires the corresponding API key to be set.

Next step: pipe real Deepgram transcript chunks here as scammer_text;
           stream ElevenLabs TTS on the utterance back through Twilio.
"""

import json
import logging
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.persona import PersonaResult
from backend.app.config import settings
from backend.app.db.models import AgentEvent
from backend.app.services.llm_client import ChatMessage, generate_text
from backend.app.services.runtime_settings import get_active_llm_provider, get_dialogue_preferences

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "betty_responses.json"


def normalize_chat_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Merge consecutive turns with the same role.

    Gemini and Anthropic expect strict user/model(or assistant) alternation. The voice
    pipeline can accidentally produce two `user` messages in a row (e.g. transcript
    edge cases); merging fixes degraded or empty model output without losing text.
    """
    out: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] = f"{out[-1]['content']}\n\n{content}".strip()
        else:
            out.append({"role": str(role), "content": content})
    return out


class DialogueResult(BaseModel):
    """Typed output of the Dialogue Agent."""

    utterance: str   # the persona's spoken response — pass to TTS
    turn_index: int  # 0-based turn count within this call
    mocked: bool     # True when MOCK_CLAUDE=true


class DialogueAgent:
    """
    Generates the next persona utterance given the scammer's latest speech.

    Instantiate per-request (or per-call) and call ``await agent.run(...)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._fixture: list[str] | None = None
        try:
            cap = int(getattr(settings, "dialogue_max_history_messages", 4000))
        except (TypeError, ValueError):
            cap = 4000
        self._max_history_messages = max(32, cap)

    async def run(
        self,
        call_id: int,
        persona: PersonaResult,
        history: list[dict[str, str]],
        scammer_text: str,
    ) -> DialogueResult:
        """
        Generate the next spoken line for the persona.

        Args:
            call_id:      DB id of the active Call.
            persona:      Persona data from PersonaAgent.run().
            history:      Previous turns as {"role": ..., "content": ...} dicts.
                          Must alternate user/assistant, starting with user.
            scammer_text: Latest final transcript from the scammer's side.

        Returns:
            DialogueResult with the utterance to synthesise via TTS.
        """
        turn_index = len(history) // 2

        if settings.mock_claude:
            utterance = self._mock_response(turn_index)
            mocked = True
            logger.debug("DialogueAgent [mock] turn=%d: %s", turn_index, utterance[:60])
        else:
            try:
                utterance = await self._call_llm(persona, history, scammer_text)
                mocked = False
                logger.debug(
                    "DialogueAgent [%s] turn=%d: %s",
                    settings.llm_provider,
                    turn_index,
                    utterance[:60],
                )
            except Exception:
                # If the hosted LLM is misconfigured (missing key/model) we still want
                # the call loop to function during setup / demos.
                logger.exception("Hosted LLM failed; falling back to mock response.")
                utterance = self._emergency_fallback(persona=persona, scammer_text=scammer_text)
                mocked = True

        utterance = self._avoid_verbatim_repeat(utterance, history=history, scammer_text=scammer_text)
        utterance = DialogueAgent._avoid_parroting_caller(utterance, scammer_text=scammer_text, persona=persona)

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="dialogue",
            event_type="utterance_generated",
            payload={
                "scammer_input": scammer_text,
                "persona_response": utterance,
                "turn_index": turn_index,
                "mocked": mocked,
            },
        ))
        await self._db.commit()

        utterance = self._apply_persona_openers(persona=persona, turn_index=turn_index, utterance=utterance)
        return DialogueResult(utterance=utterance, turn_index=turn_index, mocked=mocked)

    @staticmethod
    def _emergency_fallback(*, persona: PersonaResult, scammer_text: str) -> str:
        """
        Safety net when the hosted LLM fails.
        Must be on-topic and never use Grandma Betty fixture lines.
        """
        t = (scammer_text or "").strip()
        low = t.lower()
        if any(k in low for k in ["transaction", "charge", "charged", "payment", "500", "$"]):
            return (
                "I want to make sure I have this right. "
                "What’s the amount, the date, and the merchant/location for the transaction you’re talking about?"
            )
        if any(k in low for k in ["irs", "tax", "taxes", "arrest", "warrant", "case number"]):
            return (
                "Before we go further: what agency are you with, what’s my case number, "
                "and what’s the official callback number for your department?"
            )
        if any(k in low for k in ["computer", "refund", "remote", "teamviewer", "anydesk"]):
            return (
                "Before I touch anything: what company are you with, what’s the ticket/case ID, "
                "and what are you asking me to do on the computer?"
            )
        # Keep the fallback neutral (no punchlines / persona-specific riffs).
        _ = persona
        return "Sorry, I didn’t catch that. Who are you with, and what exactly do you need me to do next?"

    @staticmethod
    def _avoid_verbatim_repeat(utterance: str, *, history: list[dict[str, str]], scammer_text: str) -> str:
        """
        If the model repeats the previous persona line verbatim, force a forward-moving follow-up.
        """
        def _norm(s: str) -> str:
            import re

            s2 = s.lower()
            s2 = re.sub(r"[^a-z0-9]+", " ", s2).strip()
            return re.sub(r"\s+", " ", s2)

        last_persona = ""
        for m in reversed(history):
            if m.get("role") in {"assistant", "persona"} and isinstance(m.get("content"), str):
                last_persona = m["content"]
                break

        if last_persona and _norm(last_persona) == _norm(utterance):
            # Generic but effective: pushes the scammer to give the next concrete step.
            if any(k in scammer_text.lower() for k in ["tax", "irs", "arrest", "warrant", "case"]):
                return "What is the next step you need me to take, exactly? And what is my case number?"
            if any(k in scammer_text.lower() for k in ["computer", "refund", "remote", "teamviewer", "anydesk"]):
                return "What is the next step you need me to take on the computer, exactly?"
            return "What is the next step you need me to take, exactly?"

        # Same canned demand twice in a row (common with anchor-style personas).
        hammer = "i am asking you a simple question"
        if hammer in _norm(utterance) and hammer in _norm(last_persona):
            low = scammer_text.lower()
            if any(k in low for k in ["card", "credit", "debit", "cvv", "otp", "pin", "reverse", "fraud", "transaction", "bank"]):
                return (
                    "Hold on—you said you need my card details to reverse it. "
                    "What’s your employee ID and the official bank number I can call you back on, right now?"
                )
            return "Stop circling—what exact information do you want next, and why can’t you do this without my full card number?"

        return utterance

    @staticmethod
    def _avoid_parroting_caller(utterance: str, *, scammer_text: str, persona: PersonaResult) -> str:
        """If the model only echoed the caller's last line, replace with a forward move."""
        import re

        def _norm(s: str) -> str:
            s2 = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
            return re.sub(r"\s+", " ", s2)

        u, s = _norm(utterance), _norm(scammer_text)
        if len(s) < 4:
            return utterance
        if u == s:
            # Neutral recovery: avoid mirroring the caller verbatim.
            if persona.name == "Arnab Goswami":
                return "What do you need me to do next, and what authority are you acting under?"
            if persona.name == "Trevor Noah":
                return "What do you need me to do next?"
            return "What do you need me to do next?"

        # Near-verbatim echo of a short caller challenge (e.g. "out of character?")
        if len(s.split()) <= 8 and u in {s, s.rstrip("?"), s + "?"}:
            if persona.name == "Arnab Goswami":
                return "Let’s stay on track. What exactly are you asking me to do right now, and what happens if I don’t?"
            return "Let’s stay on track. What exactly are you asking me to do right now?"

        # Short line that is mostly a phrase lifted from their last utterance (e.g. "Out of character?").
        core = (utterance or "").strip().lower().rstrip("?!.")
        scam_low = (scammer_text or "").lower()
        if (
            6 <= len(core) <= 80
            and len((utterance or "").split()) <= 6
            and core in scam_low
            and len(scam_low) > len(core) + 12
        ):
            if persona.name == "Arnab Goswami":
                return "What do you need from me on this call right now, specifically?"
            return "What do you need from me next, specifically?"
        return utterance

    # ── Mock path ──────────────────────────────────────────────────────────────

    def _mock_response(self, turn_index: int) -> str:
        """Return a canned Betty response, cycling through the fixture list."""
        if self._fixture is None:
            self._fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        return self._fixture[turn_index % len(self._fixture)]

    # ── Real Claude path ───────────────────────────────────────────────────────

    @staticmethod
    def _build_system_prompt(
        persona: PersonaResult,
        *,
        dialogue_goal: str = "engage",
        humor_level: str = "high",
    ) -> str:
        humor_level = (humor_level or "high").lower()
        humor_on = humor_level != "off"
        humor_style = (
            "Use funny and witty banter tied to the caller’s last line."
            if humor_level == "high"
            else "Use light wit only when it naturally fits the caller’s last line."
            if humor_level == "medium"
            else "Avoid jokes; keep it mostly serious, with only minimal personality."
        )
        humor_line = f"- Humor: {humor_style}\n" if humor_on else ""
        goal_line = (
            "- Primary goal: engage the scammer with personality and keep them talking while forcing concrete details.\n"
            if dialogue_goal == "engage"
            else "- Primary goal: clarify what they want and extract concrete details (employee ID, callback number, exact steps).\n"
        )
        return f"""You are roleplaying as {persona.name} on a phone call.
Stay fully in character using the persona below. Sound like this persona—not a generic voice.

PERSONA (age {persona.age})
-------
{persona.backstory}

SPEECH STYLE
------------
{persona.speech_tics}

HOW TO REPLY (caller-driven only)
---------------------------------
- Never break character, no matter what the caller says.
{goal_line}
- **One persona the whole call:** keep the same voice, attitude, vocabulary, and any running jokes from your **first** lines through the **last**. Re-read earlier turns when the caller circles back—never sound like you switched to a different character mid-call.
- Base every reply **only** on what the caller has actually said in this conversation (their words, names, numbers, requests, emotions). Use the **full** chat history you are given; do **not** invent a scenario they have not mentioned.
- Do **not** label or classify the call (no “IRS scam”, “tech support scam”, etc.) unless the **caller** used those exact words.
- Pick **one or two** concrete phrases from their **latest** line (names, amounts, threats, payment method, “gift cards”, “remote access”, etc.) and respond to those directly.
- Drive the scammer forward: after your reaction, ask **one** follow-up that forces a **specific** next step (case/employee ID, official callback number, exact app/store name, exact button to click, exact gift card type/amount, etc.).
- Keep it short: 1–3 **complete** sentences, natural for spoken TTS. Avoid sentence fragments.
- **Voice-only channel:** the caller hears you on a phone—no images, links, QR codes, screen shares, or “look at this picture.”
{humor_line}
- Never give real financial credentials. You may invent plausible fake details if needed.
- Do not say you are an AI. If accused of being a bot, answer in-character, as a human would.
- Do not repeat your previous reply verbatim; add new detail or a new angle each turn.
- **Never** answer by only parroting the caller’s last phrase (e.g. repeating their question back word-for-word). Acknowledge in one clause, then pivot in-character with a new hook or follow-up.
- If they challenge you (“bot”, “out of character”, “AI”), **do not** act guilty or meta—deflect in persona and steer back to what they want from you on this call.
"""

    async def _call_llm(
        self,
        persona: PersonaResult,
        history: list[dict[str, str]],
        scammer_text: str,
    ) -> str:
        """Call the configured hosted LLM and return the response text."""
        trimmed_history = history[-self._max_history_messages :]
        user_turn = (
            f'Caller just said (verbatim): "{scammer_text}"\n'
            "Reply in 1–3 complete sentences for spoken voice. React to their actual words; end with one clear follow-up. "
            "Do not output sentence fragments. "
            "Do not parrot-only; do not repeat your previous reply."
        )
        raw_messages = normalize_chat_messages(
            list(trimmed_history) + [{"role": "user", "content": user_turn}]
        )
        messages = cast(list[ChatMessage], raw_messages)
        provider = await get_active_llm_provider(self._db)
        prefs = await get_dialogue_preferences(self._db)
        goal = prefs.get("dialogue_goal", "engage")
        humor = prefs.get("humor_level", "high")
        try:
            max_out = int(getattr(settings, "dialogue_max_output_tokens", 2048))
        except (TypeError, ValueError):
            max_out = 2048
        # Providers require a finite value; treat non-positive as "very high".
        if max_out <= 0:
            max_out = 2048
        text = await generate_text(
            provider=provider,
            system=self._build_system_prompt(persona, dialogue_goal=goal, humor_level=humor),
            messages=messages,
            max_tokens=max_out,
        )
        if not (text or "").strip():
            raise RuntimeError("Hosted LLM returned empty text")
        utterance = self._post_process_utterance(text)
        utterance = self._apply_persona_constraints(persona, utterance)
        utterance = self._ensure_non_fragment(persona=persona, utterance=utterance, scammer_text=scammer_text)
        return utterance

    @staticmethod
    def _ensure_non_fragment(*, persona: PersonaResult, utterance: str, scammer_text: str) -> str:
        """
        Guard against low-quality fragment outputs like "Oh, my stars, you."
        When these slip through, the call feels broken and the bot tends to repeat itself.
        """
        import re

        u = (utterance or "").strip()
        if not u:
            return DialogueAgent._emergency_fallback(persona=persona, scammer_text=scammer_text)

        toks = u.split()
        looks_fragmenty = (
            len(toks) <= 5
            and "?" not in u
            and not re.search(r"\b(because|so|but|and)\b", u.lower())
        )
        if not looks_fragmenty:
            return u

        low = (scammer_text or "").lower()
        creds = ["credit card", "card number", "cvv", "otp", "pin", "debit card"]

        # Persona-specific recovery so every persona sounds coherent (no fragments),
        # while still forcing the scammer to explain the next step.
        if persona.name == "Russell Peters":
            if any(k in low for k in creds):
                return (
                    "That’s cute. Why would I give you my card details—what’s your employee ID "
                    "and the official callback number?"
                )
            return "Okay—slow down. What exactly do you need from me next, and why?"
        if persona.name == "Jimmy Fallon":
            if any(k in low for k in creds):
                return "Nice try. What’s your employee ID and the official number I can call back—then we’ll talk."
            return "Okay—what exactly do you need me to do next?"
        if persona.name == "Samay Raina":
            if any(k in low for k in creds):
                return "Card details? Bold. What’s your employee ID and the official callback number first?"
            return "Okay—what’s the next step you want me to do?"
        if persona.name == "Ronny Chieng":
            if any(k in low for k in creds):
                return "No. What’s your employee ID and your official callback number? Then explain why you need my card."
            return "What exactly do you want me to do next?"
        if persona.name == "Trevor Noah":
            if any(k in low for k in creds):
                return "Okay, but why would you need my card details for that? What’s your employee ID and the official number to call back?"
            return "Okay—what exactly do you need me to do next?"
        if persona.name == "Arnab Goswami":
            if any(k in low for k in creds):
                return "Absolutely not. What is your employee ID, what is the official callback number, and why are you asking for card details?"
            return "Answer me clearly: who are you with, and what exactly do you want me to do next?"
        if persona.name == "Miranda Priestly":
            if any(k in low for k in creds):
                return "No. Give me your employee ID and the official callback number. Then explain why you need card details."
            return "Be precise. What do you need me to do next?"
        if persona.name == "Parrot (Home Alone Vibe)":
            if any(k in low for k in creds):
                return "Squawk—nope. What’s your employee ID and the number I can call you back on?"
            return "Squawk—what do you want me to do next?"
        if persona.name == "Grandma Betty":
            if any(k in low for k in creds):
                return "Oh honey, I’m not giving card numbers on the phone. What’s your name and the official number I can call back?"
            return "Oh dear—say that again. What do you need me to do next?"

        return DialogueAgent._emergency_fallback(persona=persona, scammer_text=scammer_text)

    @staticmethod
    def _apply_persona_constraints(persona: PersonaResult, utterance: str) -> str:
        """
        Light cleanup only. Heavy-handed punctuation rules were mangling good LLM output
        and breaking conversational flow on the phone.
        """
        if persona.name == "Arnab Goswami":
            import re

            utterance = re.sub(r",\s*Mr\.\s*$", "", utterance, flags=re.IGNORECASE)
            utterance = re.sub(r"\bMr\.\s*,\s*Mr\.\b", "Mr.", utterance, flags=re.IGNORECASE)
            utterance = utterance.strip()
            if "?" in utterance and not utterance.endswith("?"):
                last_q = utterance.rfind("?")
                tail = utterance[last_q + 1 :].strip()
                if tail and len(tail) < 80:
                    utterance = utterance[: last_q + 1].strip()
        return utterance

    @staticmethod
    def _apply_persona_openers(persona: PersonaResult, turn_index: int, utterance: str) -> str:
        # Opening “monkey butt” line is spoken on call pickup in `voice.incoming`; avoid duplicating here.
        return utterance

    @staticmethod
    def _post_process_utterance(text: str) -> str:
        cleaned = " ".join((text or "").replace("\n", " ").split()).strip()
        if not cleaned:
            return "Sorry—could you repeat that a little slower?"

        # Drop useless leading fragment sentences like "The." / "And." / "But." caused by truncation.
        import re

        cleaned = re.sub(r"^(the|and|but|so|well|uh|um)\.\s+", "", cleaned, flags=re.IGNORECASE)
        # If it's STILL just a stranded article/conjunction, bail to a sane reprompt.
        if re.fullmatch(r"(the|and|but|so|well|uh|um)\.?", cleaned.strip(), flags=re.IGNORECASE):
            return "Hold on—say that again for me. What’s the very next step you need me to do?"

        # Split into sentences; remove tiny broken fragments anywhere in the output
        # (e.g. "The.", "You.", "Okay.", caused by model truncation or odd decoding).
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", cleaned) if p.strip()]
        junk_words = {"the", "and", "but", "so", "well", "uh", "um", "you", "ok", "okay", "yeah"}
        filtered: list[str] = []
        for p in parts:
            toks = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip().split()
            if len(toks) <= 2 and toks and toks[0] in junk_words:
                continue
            filtered.append(p)
        parts = filtered

        # De-dupe accidental repeated sentences.
        if len(parts) >= 2:
            deduped: list[str] = []
            seen_norm: set[str] = set()
            for p in parts:
                norm = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                deduped.append(p)
            parts = deduped
        cleaned = " ".join(parts).strip()

        # Fix a common incomplete tail: "... is that a?" / "... is that an?"
        if re.search(r"\bis that (a|an)\?$", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(r"\bis that (a|an)\?$", "is that exactly?", cleaned, flags=re.IGNORECASE).strip()
        # keep it phone-call short for latency and natural rhythm, but preserve sentence boundaries
        try:
            cap = int(getattr(settings, "dialogue_max_utterance_chars", 900))
        except (TypeError, ValueError):
            cap = 900
        cap = max(240, min(2000, cap))
        if len(cleaned) > cap:
            for end in [".", "!", "?"]:
                idx = cleaned[:cap].rfind(end)
                if idx > 120:
                    cleaned = cleaned[: idx + 1].strip()
                    break
            else:
                cleaned = cleaned[:cap].rsplit(" ", 1)[0].strip()
        # If upstream cut mid-thought, remove a dangling 1–2 char tail token (common on token cutoffs).
        toks = cleaned.split()
        if len(toks) >= 3 and len(toks[-1]) <= 2 and toks[-1].lower() not in {"i", "a", "ok", "no", "so"}:
            cleaned = " ".join(toks[:-1]).strip()
        # Guard against low-quality fragment outputs like "Oh, my stars, you."
        # If we still got a fragment, force a complete, forward-moving question.
        toks2 = cleaned.split()
        if len(toks2) <= 5 and "?" not in cleaned:
            return "Okay. What exactly do you need me to do next?"
        if cleaned and cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."
        return cleaned

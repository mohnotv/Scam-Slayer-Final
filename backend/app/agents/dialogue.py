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
from backend.app.services.runtime_settings import get_active_llm_provider

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "betty_responses.json"


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
            return "Hold on—did you say there was a 500-dollar transaction? On what date, and where exactly did it happen?"
        if any(k in low for k in ["irs", "tax", "taxes", "arrest", "warrant", "case number"]):
            return "Okay, wait—who are you with, and what’s my case number? And what do you need me to do first?"
        if any(k in low for k in ["computer", "refund", "remote", "teamviewer", "anydesk"]):
            return "Alright—what’s the very first step you want me to do on the computer? Tell me exactly what to click."
        # Persona-aware tone tweak: Arnab ends with a demand.
        if persona.name == "Arnab Goswami":
            return "You are not answering the question. Who are you, and what is the allegation—yes or no?"
        if persona.name == "Trevor Noah":
            return "Hold on—wait wait wait, what did you say just now? Who are you with, and what do you need me to do?"
        return "Sorry—repeat that for me. Who are you with, and what do you need me to do next?"

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
                return "Okay, okay—so what’s the very next step, exactly? And what’s my case number again?"
            if any(k in scammer_text.lower() for k in ["computer", "refund", "remote", "teamviewer", "anydesk"]):
                return "Alright—what’s the very next click you need me to do, exactly? Slow like I’m five."
            return "Alright—what’s the very next step you need me to do, exactly?"

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
            if persona.name == "Arnab Goswami":
                return "I’m right here on the line—stop stalling. What do you want me to do next, and under what authority?"
            if persona.name == "Trevor Noah":
                return "Okay, I’m listening—what’s the actual play here? What do you need from me?"
            return "I heard you—go on. What’s the next step you’re asking for?"

        # Near-verbatim echo of a short caller challenge (e.g. "out of character?")
        if len(s.split()) <= 8 and u in {s, s.rstrip("?"), s + "?"}:
            if persona.name == "Arnab Goswami":
                return "This is a phone line, not a therapy session—make your charge or move on. What happens next if I don’t comply?"
            return "Cute—let’s stay on track. What exactly are you trying to get me to do right now?"

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
                return "You’re doing theatre—I’m doing cross-examination. What do you need from me on this call, right now?"
            return "I’m with you—keep going. What’s the actual next step you want?"
        return utterance

    # ── Mock path ──────────────────────────────────────────────────────────────

    def _mock_response(self, turn_index: int) -> str:
        """Return a canned Betty response, cycling through the fixture list."""
        if self._fixture is None:
            self._fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        return self._fixture[turn_index % len(self._fixture)]

    # ── Real Claude path ───────────────────────────────────────────────────────

    @staticmethod
    def _build_system_prompt(persona: PersonaResult) -> str:
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
- **One persona the whole call:** keep the same voice, attitude, vocabulary, and any running jokes from your **first** lines through the **last**. Re-read earlier turns when the caller circles back—never sound like you switched to a different character mid-call.
- Base every reply **only** on what the caller has actually said in this conversation (their words, names, numbers, requests, emotions). Use the **full** chat history you are given; do **not** invent a scenario they have not mentioned.
- Do **not** label or classify the call (no “IRS scam”, “tech support scam”, etc.) unless the **caller** used those exact words.
- Pick **one or two** concrete phrases from their **latest** line and respond to those directly. Then ask **one** clear follow-up that makes them explain the **next** step in **their** story.
- Keep it short: 1–3 complete sentences, natural for spoken TTS.
- **Voice-only channel:** the caller hears you on a phone—no images, links, QR codes, screen shares, or “look at this picture.” Humor must be **spoken** only (wordplay, mock-innocence, silly exaggeration, a sharp one-liner)—**always tied to their last line**, never random roast.
- Humor should feel like banter on a phone call: playful, surprising, but still pushing their story forward with your follow-up question.
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
        early_call = len(trimmed_history) < 6
        wit_note = (
            "This is still near the top of the call—bring a little extra spark: a quick joke or teasing aside "
            "that fits what they just said (still voice-only, still in-character). "
            if early_call
            else ""
        )
        user_turn = (
            f'The caller\'s latest words (verbatim): "{scammer_text}"\n\n'
            "Reply in 1–3 short sentences for spoken voice only (nothing visual). "
            "React to what they literally said; quote or paraphrase at least one concrete detail from that line. "
            "Include a witty or funny beat if it fits naturally (still grounded in their words, sayable on a phone). "
            f"{wit_note}"
            "Ask exactly one follow-up about the next thing *they* are trying to get you to do—using their wording, not a new script. "
            "Do not repeat your previous reply or reuse the same closing sentence. "
            "Do not echo only their latest words—always add your own in-character spin and a forward-moving question."
        )
        raw_messages = list(trimmed_history) + [{"role": "user", "content": user_turn}]
        messages = cast(list[ChatMessage], raw_messages)
        provider = await get_active_llm_provider(self._db)
        text = await generate_text(
            provider=provider,
            system=self._build_system_prompt(persona),
            messages=messages,
            max_tokens=180,
        )
        utterance = self._post_process_utterance(text)
        utterance = self._apply_persona_constraints(persona, utterance)
        return utterance

    @staticmethod
    def _apply_persona_constraints(persona: PersonaResult, utterance: str) -> str:
        # Trevor: always end with a question/hook (spoken cadence).
        if persona.name == "Trevor Noah":
            # If it ends with a period (or nothing), convert to a question.
            if utterance and utterance[-1] == "." and "?" not in utterance:
                utterance = utterance[:-1] + "?"
            if "?" not in utterance:
                # Gentle hook without forcing a specific topic.
                utterance = (utterance.rstrip(".! ") + "—right?").strip()
                if utterance and utterance[-1] != "?":
                    utterance = utterance + "?"
        # Arnab: end with a sharp question; avoid mechanically appending the same "simple question" line (causes loops).
        if persona.name == "Arnab Goswami":
            import re

            utterance = re.sub(r",\s*Mr\.\s*$", "", utterance, flags=re.IGNORECASE)
            utterance = re.sub(r"\bMr\.\s*,\s*Mr\.\b", "Mr.", utterance, flags=re.IGNORECASE)
            utterance = utterance.strip()
            # If the model already asked a question, then tacked on a fragment ("...? I am listening very"),
            # drop the dangling tail so we don't glue "—yes or no?" onto broken half-sentences.
            if "?" in utterance and not utterance.endswith("?"):
                last_q = utterance.rfind("?")
                tail = utterance[last_q + 1 :].strip()
                if tail and len(tail) < 80:
                    utterance = utterance[: last_q + 1].strip()

            # Arnab should sound prosecutorial, but a canned "yes or no" every turn reads
            # robotic on the phone (and loops). Only ensure a sentence ending.
            if utterance and utterance[-1] not in "?!.…":
                utterance = utterance.rstrip(",;- ") + "?"
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

        # De-dupe accidental repeated sentences (common when we append persona constraints).
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", cleaned) if p.strip()]
        if len(parts) >= 2:
            deduped: list[str] = []
            seen_norm: set[str] = set()
            for p in parts:
                norm = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                deduped.append(p)
            cleaned = " ".join(deduped).strip()
        # keep it phone-call short for latency and natural rhythm, but preserve sentence boundaries
        if len(cleaned) > 340:
            for end in [".", "!", "?"]:
                idx = cleaned[:340].rfind(end)
                if idx > 120:
                    cleaned = cleaned[: idx + 1].strip()
                    break
            else:
                cleaned = cleaned[:340].rsplit(" ", 1)[0].strip()
        # If upstream cut mid-thought, remove a dangling 1–2 char tail token (common on token cutoffs).
        toks = cleaned.split()
        if len(toks) >= 2 and len(toks[-1]) <= 2 and toks[-1].lower() not in {"i", "a", "ok"}:
            cleaned = " ".join(toks[:-1]).strip()
        if cleaned and cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."
        return cleaned

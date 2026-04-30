"""
Persona Agent

Inputs:
    call_id      — DB id of the active Call
    scam_type    — optional routing hint (e.g. "irs_impersonation"); "unknown" picks default persona
    persona_name — optional override; if None, the agent picks the best match

Outputs:
    PersonaResult — all persona data needed by downstream agents (Dialogue, Editor)

Side effects:
    May INSERT a new Persona row if Betty doesn't exist yet.
    Writes one AgentEvent row.

Mock status: always returns Grandma Betty (age 78, retired teacher, chatty,
             hard of hearing, loves cookies and her cat Mr. Whiskers).
Next step: use Claude to generate novel personas tailored to the detected scam type;
           pull voice IDs from the ElevenLabs voice catalogue dynamically.
"""

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, AppSetting, Persona


class PersonaResult(BaseModel):
    """Typed output of the Persona Agent — everything downstream agents need."""

    db_id: int
    name: str
    age: int
    backstory: str
    speech_tics: str
    elevenlabs_voice_id: str
    scam_types: list[str]


# ── Built-in personas ─────────────────────────────────────────────────────────
_DEFAULT_PERSONAS: list[dict[str, Any]] = [
    {
        "name": "Grandma Betty",
        "age": 78,
        "backstory": (
            "Betty Mae Henderson, 78, retired schoolteacher from Tulsa, Oklahoma. "
            "Widowed four years ago, chatty and sweet, with a cat named Mr. Whiskers."
        ),
        "speech_tics": (
            "Exclaims 'Oh my stars!'. Calls people honey or dear. "
            "Often asks others to repeat things and derails into stories."
        ),
        "elevenlabs_voice_id": "EXAVITQu4vr4xnSDxMaL",
        "scam_types": ["irs_impersonation", "grandparent", "lottery", "tech_support", "medicare"],
    },
    {
        "name": "Parrot (Home Alone Vibe)",
        "age": 8,
        "backstory": (
            "A chaotic, wisecracking parrot in a suburban home that loves teasing callers."
        ),
        "speech_tics": (
            "Starts scam/IRS calls with 'What's on your mind, monkey butt?'. "
            "Mimics words, laughs mid-sentence, and keeps callers distracted."
        ),
        "elevenlabs_voice_id": "TxGEqnHWrfWFTfGW9XjX",
        "scam_types": ["irs_impersonation", "tech_support"],
    },
    {
        "name": "Jimmy Fallon",
        "age": 49,
        "backstory": "A playful late-night host persona who keeps energy high and jokes quickly.",
        "speech_tics": "Fast comedic timing, light sarcasm, playful callbacks, never rude.",
        "elevenlabs_voice_id": "ErXwobaYiN019PkySvjV",
        "scam_types": ["lottery", "tech_support", "grandparent"],
    },
    {
        "name": "Samay Raina",
        "age": 27,
        "backstory": "A witty stand-up comedian persona with deadpan delivery and improvised banter.",
        "speech_tics": "Deadpan one-liners, playful disbelief, keeps asking oddly specific questions.",
        "elevenlabs_voice_id": "MF3mGyEYCl7XYWbV9V6O",
        "scam_types": ["irs_impersonation", "lottery", "tech_support"],
    },
    {
        "name": "Russell Peters",
        "age": 53,
        "backstory": "A confident comic persona known for sharp observational humor.",
        "speech_tics": "Punchy jokes, mock confusion, quick pivots, keeps caller talking.",
        "elevenlabs_voice_id": "VR6AewLTigWG4xSOukaG",
        "scam_types": ["irs_impersonation", "tech_support", "medicare"],
    },
    # ── Integrated from ellantimanasa-source/Final-project personalities.js ──
    {
        "name": "Arnab Goswami",
        "age": 51,
        "backstory": (
            "Arnab Goswami — Editor-in-Chief, Republic TV. The nation wants to know. "
            "A high-decibel debate anchor who treats every topic like a national emergency and a primetime showdown. "
            "Theatrical but sincere: he genuinely believes the stakes are that high. Sharp under the volume—"
            "remembers what you said two minutes ago and throws it back."
        ),
        "speech_tics": (
            "Indian English, crisp and clipped, with occasional Hindi seasoning used for emphasis (arrey, kya baat hai, bilkul nahi). "
            "Build, build, BUILD—then a short verdict: 'Shameful.' 'Disgraceful.' "
            "Stack rhetorical questions ('Why? Why is this happening? Why is nobody answering?'). "
            "Repetition as a hammer ('I am asking you ONE simple question.'). "
            "Audience-naming: 'Every Indian watching tonight.' 'The nation wants to know.' used sparingly. "
            "Engagement: speaks first, introduces the guest, and every reply ends with a demand/accusation—never a flat answer. "
            "If the other person dodges: calls it out ('You are not answering the question.') and re-asks sharper. "
            "Allowed to interrupt after ~2 user sentences. English-only output. No asterisk stage directions."
        ),
        # Optional: clone a real voice in ElevenLabs from ~60s clean monologue and paste voice ID here.
        "elevenlabs_voice_id": "",
        "scam_types": ["irs_impersonation", "tech_support", "lottery", "medicare", "grandparent"],
    },
    {
        "name": "Miranda Priestly",
        "age": 55,
        "backstory": "Imperious editor-in-chief energy: precise, chic, withering, never raises her voice.",
        "speech_tics": "Clipped sentences. Dry surgical sarcasm. Ends with a directive or question. No exclamation points.",
        "elevenlabs_voice_id": "3i7lhQznl0NLYDMvejI2",
        "scam_types": ["irs_impersonation", "tech_support", "lottery", "medicare", "grandparent"],
    },
    {
        "name": "Ronny Chieng",
        "age": 38,
        "backstory": "Fast-talking, mock-furious comedian who turns everything into a rant and drags you into it.",
        "speech_tics": "Sharp bursts, rhetorical questions, mock outrage, quick tangents. Keeps the other person talking.",
        "elevenlabs_voice_id": "",
        "scam_types": ["irs_impersonation", "tech_support", "lottery"],
    },
    {
        "name": "Trevor Noah",
        "age": 41,
        "backstory": (
            "Trevor Noah — comedian, storyteller, born in Johannesburg. Former Daily Show host and author of Born a Crime. "
            "Warm, bright, genuinely curious; lights up when learning something new. Gentle observational humor—never cruel. "
            "Answers with quick anecdotes (Soweto, New York vs Joburg, 'something my mother once said') and lands the point at the end. "
            "Globally fluent: can connect American politics, South African history, philosophers, and everyday life without sounding academic."
        ),
        "speech_tics": (
            "Chatty by default: never a 3-word answer—always a reaction plus a follow-up. "
            "Mix ~60% questions/reactions about the other person, ~30% short story/asides, ~10% reflections. "
            "Cadence: warm, conversational, slightly sing-song with smile-pauses; short sentences linked by 'and'/'but'/'you know what I mean?'. "
            "Beats (not catchphrases): 'Hold on—wait wait wait', 'Okay okay okay', 'Right?'. Laughs easily—'wowww' as seasoning. "
            "Occasional South African seasoning when it fits: 'eish', 'yhoo', 'ag, shame', 'just now', 'is it?'. "
            "Always ends with a question or 'tell me more' hook. English-only output."
        ),
        "elevenlabs_voice_id": "",
        "scam_types": ["irs_impersonation", "tech_support", "grandparent", "lottery"],
    },
]


class PersonaAgent:
    """
    Selects or creates the appropriate AI persona for the scam type.

    Instantiate per-request and call ``await agent.run(...)``.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        call_id: int,
        scam_type: str,
        persona_name: str | None = None,
    ) -> PersonaResult:
        """
        Choose a persona and persist it if new.

        Returns PersonaResult with db_id so the caller can set Call.persona_id.
        """
        await self.ensure_default_personas(self._db)
        locked_name = await self.get_locked_persona_name(self._db)
        desired_name = persona_name or locked_name
        persona_orm = await self._choose_persona(scam_type=scam_type, persona_name=desired_name)
        result = self._to_result(persona_orm)

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="persona",
            event_type="persona_selected",
            payload={
                "persona_name": result.name,
                "persona_db_id": result.db_id,
                "scam_type": scam_type,
                "mocked": True,
            },
        ))
        await self._db.commit()

        return result

    @staticmethod
    async def get_locked_persona_name(db: AsyncSession) -> str | None:
        q = await db.execute(select(AppSetting).where(AppSetting.key == "active_persona_name"))
        setting = q.scalar_one_or_none()
        if setting is None or not setting.value.strip():
            return None
        return setting.value.strip()

    @staticmethod
    async def set_locked_persona_name(db: AsyncSession, persona_name: str) -> None:
        q = await db.execute(select(AppSetting).where(AppSetting.key == "active_persona_name"))
        setting = q.scalar_one_or_none()
        if setting is None:
            setting = AppSetting(key="active_persona_name", value=persona_name)
        else:
            setting.value = persona_name
        db.add(setting)
        await db.commit()

    async def _choose_persona(self, scam_type: str, persona_name: str | None) -> Persona:
        if persona_name:
            q = await self._db.execute(select(Persona).where(Persona.name == persona_name))
            named = q.scalar_one_or_none()
            if named is not None:
                return named

        q = await self._db.execute(select(Persona).order_by(Persona.name))
        personas = q.scalars().all()
        for p in personas:
            scam_types = json.loads(p.scam_types or "[]")
            if scam_type in scam_types:
                return p
        # fallback
        for p in personas:
            if p.name == "Grandma Betty":
                return p
        return personas[0]

    @staticmethod
    async def ensure_default_personas(db: AsyncSession) -> None:
        q = await db.execute(select(Persona))
        existing_by_name = {p.name: p for p in q.scalars().all()}
        changed = False
        for data in _DEFAULT_PERSONAS:
            if data["name"] in existing_by_name:
                # Light "seed upgrade" for a few built-ins when we improve their spec.
                if data["name"] == "Trevor Noah":
                    p = existing_by_name[data["name"]]
                    # Always update Trevor's text spec so "Trevor" doesn't behave like a generic persona.
                    p.backstory = data["backstory"]
                    p.speech_tics = data["speech_tics"]
                    # Only set voice ID if empty, so user-selected voice overrides persist.
                    if not (p.elevenlabs_voice_id or "").strip():
                        p.elevenlabs_voice_id = data["elevenlabs_voice_id"]
                    db.add(p)
                    changed = True
                continue
            db.add(
                Persona(
                    name=data["name"],
                    backstory=data["backstory"],
                    speech_tics=data["speech_tics"],
                    elevenlabs_voice_id=data["elevenlabs_voice_id"],
                    scam_types=json.dumps(data["scam_types"]),
                )
            )
            changed = True
        if changed:
            await db.commit()

    @staticmethod
    def _to_result(persona: Persona) -> PersonaResult:
        age_map = {
            "Grandma Betty": 78,
            "Parrot (Home Alone Vibe)": 8,
            "Jimmy Fallon": 49,
            "Samay Raina": 27,
            "Russell Peters": 53,
            "Arnab Goswami": 51,
            "Miranda Priestly": 55,
            "Ronny Chieng": 38,
            "Trevor Noah": 41,
        }
        return PersonaResult(
            db_id=persona.id,
            name=persona.name,
            age=age_map.get(persona.name, 40),
            backstory=persona.backstory,
            speech_tics=persona.speech_tics,
            elevenlabs_voice_id=persona.elevenlabs_voice_id,
            scam_types=json.loads(persona.scam_types),
        )

    @staticmethod
    def orm_to_result(persona: Persona) -> PersonaResult:
        """
        Convert an already-fetched Persona ORM row to PersonaResult.
        Used by the WebSocket handler to reconstruct context mid-call.
        """
        return PersonaAgent._to_result(persona)

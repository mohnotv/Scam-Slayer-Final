"""
SQLAlchemy ORM models — SQLAlchemy 2.x declarative style.

Tables: Persona, Call, TranscriptSegment, Highlight, Clip, AgentEvent
Every agent logs structured JSON events to `agent_events` so the dashboard
can replay any call.
"""

import json
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    backstory: Mapped[str] = mapped_column(Text, nullable=False)
    speech_tics: Mapped[str] = mapped_column(Text, default="")
    elevenlabs_voice_id: Mapped[str] = mapped_column(String(100), default="")
    scam_types: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    calls: Mapped[list["Call"]] = relationship("Call", back_populates="persona")

    @property
    def scam_types_list(self) -> list[str]:
        return json.loads(self.scam_types)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    twilio_call_sid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    caller_number: Mapped[str] = mapped_column(String(50), default="unknown")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_scam: Mapped[bool] = mapped_column(Boolean, default=False)
    scam_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    scam_type: Mapped[str] = mapped_column(String(100), default="unknown")
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active|ended|error

    persona: Mapped["Persona | None"] = relationship("Persona", back_populates="calls")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        "TranscriptSegment", back_populates="call"
    )
    highlights: Mapped[list["Highlight"]] = relationship("Highlight", back_populates="call")
    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="call")
    agent_events: Mapped[list["AgentEvent"]] = relationship("AgentEvent", back_populates="call")


class TranscriptSegment(Base):
    """One chunk of transcribed speech — either from the scammer (STT) or the persona (TTS input).

    Rows accumulate in real-time during a call. `is_final=False` rows are partial STT results
    that may be superseded by a later final segment at the same timestamp.
    """

    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    speaker: Mapped[str] = mapped_column(String(20), default="unknown")  # "scammer" | "persona"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(Integer, default=0)  # ms from call start
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)  # STT confidence 0-1
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call: Mapped["Call"] = relationship("Call", back_populates="transcript_segments")


class Highlight(Base):
    __tablename__ = "highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), default="")  # e.g. "frustration spike"
    score: Mapped[float] = mapped_column(Float, default=0.0)  # virality score 0-1
    transcript_snippet: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call: Mapped["Call"] = relationship("Call", back_populates="highlights")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|ready|error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call: Mapped["Call"] = relationship("Call", back_populates="clips")


class AgentEvent(Base):
    """Structured log of every agent action — powers the dashboard replay."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "dialogue"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    call: Mapped["Call"] = relationship("Call", back_populates="agent_events")

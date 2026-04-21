"""
Personas REST API

GET    /personas         — list all personas
POST   /personas         — create a new persona
GET    /personas/{id}    — fetch one persona
PUT    /personas/{id}    — update a persona
DELETE /personas/{id}    — delete a persona
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import Persona
from backend.app.db.session import get_db

router = APIRouter(prefix="/personas", tags=["personas"])


class PersonaIn(BaseModel):
    name: str
    backstory: str
    speech_tics: str = ""
    elevenlabs_voice_id: str = ""
    scam_types: list[str] = []


class PersonaOut(BaseModel):
    id: int
    name: str
    backstory: str
    speech_tics: str
    elevenlabs_voice_id: str
    scam_types: list[str]

    model_config = {"from_attributes": True}


def _to_out(p: Persona) -> PersonaOut:
    return PersonaOut(
        id=p.id,
        name=p.name,
        backstory=p.backstory,
        speech_tics=p.speech_tics,
        elevenlabs_voice_id=p.elevenlabs_voice_id,
        scam_types=json.loads(p.scam_types),
    )


@router.get("", response_model=list[PersonaOut])
async def list_personas(db: AsyncSession = Depends(get_db)) -> list[PersonaOut]:
    result = await db.execute(select(Persona).order_by(Persona.name))
    return [_to_out(p) for p in result.scalars().all()]


@router.post("", response_model=PersonaOut, status_code=201)
async def create_persona(body: PersonaIn, db: AsyncSession = Depends(get_db)) -> PersonaOut:
    persona = Persona(
        name=body.name,
        backstory=body.backstory,
        speech_tics=body.speech_tics,
        elevenlabs_voice_id=body.elevenlabs_voice_id,
        scam_types=json.dumps(body.scam_types),
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return _to_out(persona)


@router.get("/{persona_id}", response_model=PersonaOut)
async def get_persona(persona_id: int, db: AsyncSession = Depends(get_db)) -> PersonaOut:
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return _to_out(persona)


@router.put("/{persona_id}", response_model=PersonaOut)
async def update_persona(
    persona_id: int, body: PersonaIn, db: AsyncSession = Depends(get_db)
) -> PersonaOut:
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    persona.name = body.name
    persona.backstory = body.backstory
    persona.speech_tics = body.speech_tics
    persona.elevenlabs_voice_id = body.elevenlabs_voice_id
    persona.scam_types = json.dumps(body.scam_types)
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return _to_out(persona)


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(persona_id: int, db: AsyncSession = Depends(get_db)) -> None:
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = result.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    await db.delete(persona)
    await db.commit()

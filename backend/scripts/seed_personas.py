"""
Seed the personas table with the default cast of characters.
Run: python -m backend.scripts.seed_personas
"""

import asyncio
import json

from backend.app.db.session import AsyncSessionLocal, init_db
from backend.app.db.models import Persona

PERSONAS = [
    {
        "name": "Grandma Betty",
        "backstory": (
            "Betty Mae Henderson, 78, retired schoolteacher from Tulsa, Oklahoma. "
            "Widowed 4 years ago. Dotes on her 6 grandchildren. Hard of hearing, "
            "frequently loses track of sentences. Her cat Mr. Whiskers is a recurring topic."
        ),
        "speech_tics": "Says 'Oh my stars!' Calls everyone 'honey'. Mentions Mr. Whiskers unprompted.",
        "elevenlabs_voice_id": "EXAVITQu4vr4xnSDxMaL",
        "scam_types": json.dumps(["irs_impersonation", "grandparent", "lottery", "tech_support"]),
    },
    {
        "name": "Forgetful Frank",
        "backstory": (
            "Frank Kowalski, 82, retired plumber from Buffalo. Keeps forgetting why he answered "
            "the phone. Has to put the phone down to find his glasses repeatedly. "
            "Tells long, meandering stories about his bowling league."
        ),
        "speech_tics": "Says 'Now where was I?' frequently. Mentions his bowling league. Shouts accidentally.",
        "elevenlabs_voice_id": "VR6AewLTigWG4xSOukaG",
        "scam_types": json.dumps(["irs_impersonation", "medicare", "tech_support"]),
    },
]


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        for data in PERSONAS:
            result = await db.execute(select(Persona).where(Persona.name == data["name"]))
            existing = result.scalar_one_or_none()
            if existing is None:
                db.add(Persona(**data))
                print(f"Created: {data['name']}")
            else:
                print(f"Already exists: {data['name']}")
        await db.commit()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

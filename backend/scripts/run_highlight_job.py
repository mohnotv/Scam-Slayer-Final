"""
Manual trigger for the post-call highlight mining + clip generation pipeline.
Useful for re-processing a call or testing the pipeline locally.

Usage:
    python -m backend.scripts.run_highlight_job --call-id 3
"""

import argparse
import asyncio

from backend.app.agents.editor import assemble_clip
from backend.app.agents.highlights import mine_highlights
from backend.app.agents.social import generate_social_package
from backend.app.db.session import AsyncSessionLocal, init_db
from backend.app.db.models import Call
from sqlalchemy import select


async def main(call_id: int) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Call).where(Call.id == call_id))
        call = result.scalar_one_or_none()
        if call is None:
            print(f"Call {call_id} not found.")
            return

        print(f"Mining highlights for call {call_id}…")
        highlights = await mine_highlights(call_id, db)
        print(f"  Found {len(highlights)} highlights.")

        print("Assembling clip…")
        clip = await assemble_clip(call_id, highlights, audio_path=None, db=db)
        print(f"  Clip id={clip.id}, status={clip.status}")

        print("Generating social package…")
        pkg = await generate_social_package(call_id, clip, call, highlights, db)
        print(f"  Caption: {pkg.caption[:80]}…")
        print(f"  Hashtags: {pkg.hashtags}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.call_id))

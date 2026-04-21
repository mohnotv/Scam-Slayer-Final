"""
Manual trigger for the post-call highlight mining + clip generation pipeline.
Useful for re-processing a call or testing the pipeline locally.

Usage:
    python -m backend.scripts.run_highlight_job --call-id 3
"""

import argparse
import asyncio

from sqlalchemy import select

from backend.app.agents.editor import EditorAgent
from backend.app.agents.highlights import HighlightMinerAgent
from backend.app.agents.social import SocialAgent
from backend.app.db.models import Call
from backend.app.db.session import AsyncSessionLocal, init_db


async def main(call_id: int) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        call_q = await db.execute(select(Call).where(Call.id == call_id))
        call = call_q.scalar_one_or_none()
        if call is None:
            print(f"Call {call_id} not found.")
            return

        print(f"Mining highlights for call {call_id}…")
        highlights = await HighlightMinerAgent(db).run(call_id)
        print(f"  Found {len(highlights.highlights)} highlights.")

        print("Assembling clip…")
        editor_result = await EditorAgent(db).run(call_id, highlights, audio_path=None)
        print(f"  Clip db_id={editor_result.db_id}, status={editor_result.status}")
        print(f"  File: {editor_result.file_path}")

        print("Generating social package…")
        social_result = await SocialAgent(db).run(
            call_id=call_id,
            clip_db_id=editor_result.db_id,
            clip_duration_seconds=editor_result.duration_seconds,
            call_duration_seconds=call.duration_seconds,
            highlights=highlights,
        )
        print(f"  Caption: {social_result.caption[:80]}…")
        print(f"  Hashtags: {social_result.hashtags}")
        print(f"  Post time: {social_result.suggested_post_time}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.call_id))

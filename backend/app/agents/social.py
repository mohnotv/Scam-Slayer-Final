"""
Social Agent

Inputs:  Clip row, Highlight rows, Call row
Outputs: caption string, hashtag list, suggested posting time
Side effects: UPDATEs Clip.caption and Clip.hashtags; logs AgentEvent

MVP status: MOCK — returns hardcoded caption and hashtags.
Next step: use Claude to write a platform-aware caption from the transcript highlights;
           run virality features (analysis/03_virality_features.ipynb) to pick post time.
"""

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AgentEvent, Call, Clip, Highlight


@dataclass
class SocialPackage:
    caption: str
    hashtags: list[str]
    suggested_post_time: str  # ISO-8601 or human label


async def generate_social_package(
    call_id: int,
    clip: Clip,
    call: Call,
    highlights: list[Highlight],
    db: AsyncSession,
) -> SocialPackage:
    """
    Generate caption, hashtags, and suggested post time for a clip.

    Args:
        call_id:    DB id of the Call.
        clip:       The rendered Clip row.
        call:       The Call row (scam_type, duration, etc.).
        highlights: Highlights included in the clip.
        db:         Async DB session.

    Returns:
        SocialPackage with all fields populated.
    """
    package = _generate_mock(call, highlights)

    clip.caption = package.caption
    clip.hashtags = json.dumps(package.hashtags)
    db.add(clip)

    event = AgentEvent(
        call_id=call_id,
        agent="social",
        event_type="social_package_generated",
        payload={
            "clip_id": clip.id,
            "caption_length": len(package.caption),
            "hashtag_count": len(package.hashtags),
            "suggested_post_time": package.suggested_post_time,
        },
    )
    db.add(event)
    await db.commit()

    return package


def _generate_mock(call: Call, highlights: list[Highlight]) -> SocialPackage:
    """
    MOCK: hardcoded social package.
    Replace with Claude-powered caption writing + virality model.
    """
    best = max(highlights, key=lambda h: h.score) if highlights else None
    snippet = best.transcript_snippet[:80] if best else "…"

    return SocialPackage(
        caption=(
            f'POV: You\'re a scammer and Grandma Betty just asked about her cat '
            f'for the 4th time 😭\n\n"{snippet}…"\n\n'
            f"She kept him on for {call.duration_seconds // 60} minutes. Legend. 🫶"
        ),
        hashtags=[
            "#scambaiting",
            "#scammergotscammed",
            "#grandmabetty",
            "#AIscambait",
            "#ScamSlayer",
            "#satisfying",
            "#fyp",
        ],
        suggested_post_time="Thursday 7–9 PM ET",
    )

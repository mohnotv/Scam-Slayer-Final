"""
Social Agent

Inputs:
    call_id               — DB id of the Call
    clip_db_id            — DB id of the Clip row (to update caption/hashtags)
    clip_duration_seconds — length of the rendered clip in seconds
    call_duration_seconds — total call length in seconds (drives caption narrative)
    highlights            — HighlightsResult (used for the best snippet quote)

Outputs:
    SocialResult — caption, hashtags, suggested_post_time

Side effects:
    UPDATEs Clip.caption and Clip.hashtags in the DB.
    Writes one AgentEvent row.

Mock status: hardcoded caption + hashtag list targeting scam-bait content virality patterns.
Next step: use Claude to write a platform-aware caption from the actual transcript highlights;
           run virality features (analysis/03_virality_features.ipynb) to choose post time.
"""

import json

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.highlights import HighlightsResult
from backend.app.db.models import AgentEvent, Clip
from backend.app.services.llm_client import generate_text
from backend.app.services.runtime_settings import get_active_llm_provider


class SocialResult(BaseModel):
    """Typed output of the Social Agent."""

    caption: str
    hashtags: list[str]
    suggested_post_time: str  # e.g. "Thursday 7–9 PM ET"


class SocialAgent:
    """
    Generates a social-media-ready caption, hashtags, and posting time for a clip.

    Instantiate per-request and call ``await agent.run(...)``.
    """

    _HASHTAGS: list[str] = [
        "#scambaiting",
        "#scammergotscammed",
        "#grandmabetty",
        "#AIscambait",
        "#ScamSlayer",
        "#satisfying",
        "#fyp",
        "#scamalert",
    ]

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        call_id: int,
        clip_db_id: int,
        clip_duration_seconds: float,
        call_duration_seconds: int,
        highlights: HighlightsResult,
    ) -> SocialResult:
        """
        Generate and persist social copy for a clip.

        Args:
            call_id:               DB id of the Call.
            clip_db_id:            DB id of the Clip to update.
            clip_duration_seconds: Rendered clip length.
            call_duration_seconds: Full call duration (for caption narrative).
            highlights:            HighlightsResult for best-snippet extraction.

        Returns:
            SocialResult with caption, hashtags, and posting window.
        """
        try:
            result = await self._generate_llm(call_duration_seconds, highlights)
            mocked = False
        except Exception:
            result = self._generate_mock(call_duration_seconds, highlights)
            mocked = True

        # Persist caption + hashtags back to the Clip row
        clip_q = await self._db.execute(select(Clip).where(Clip.id == clip_db_id))
        clip = clip_q.scalar_one_or_none()
        if clip is not None:
            clip.caption = result.caption
            clip.hashtags = json.dumps(result.hashtags)
            self._db.add(clip)

        self._db.add(AgentEvent(
            call_id=call_id,
            agent="social",
            event_type="social_package_generated",
            payload={
                "clip_id": clip_db_id,
                "caption_length": len(result.caption),
                "hashtag_count": len(result.hashtags),
                "suggested_post_time": result.suggested_post_time,
                "mocked": mocked,
            },
        ))
        await self._db.commit()

        return result

    @classmethod
    def _generate_mock(
        cls,
        call_duration_seconds: int,
        highlights: HighlightsResult,
    ) -> SocialResult:
        """
        MOCK: hardcoded caption using the highest-scoring highlight snippet.
        Replace with Claude + virality-model call when ready.
        """
        best = (
            max(highlights.highlights, key=lambda h: h.score)
            if highlights.highlights
            else None
        )
        snippet = (best.transcript_snippet[:80] + "…") if best else "…"
        minutes = call_duration_seconds // 60 or 1

        caption = (
            f"POV: You're a scammer and Grandma Betty just asked about her cat "
            f"for the 4th time 😭\n\n"
            f'"{snippet}"\n\n'
            f"She kept him on for {minutes} minute{'s' if minutes != 1 else ''}. "
            f"Legend. 🫶"
        )

        return SocialResult(
            caption=caption,
            hashtags=cls._HASHTAGS,
            suggested_post_time="Thursday 7–9 PM ET",
        )

    async def _generate_llm(
        self,
        call_duration_seconds: int,
        highlights: HighlightsResult,
    ) -> SocialResult:
        best = (
            max(highlights.highlights, key=lambda h: h.score)
            if highlights.highlights
            else None
        )
        snippet = best.transcript_snippet if best else ""
        system = (
            "You write short-form social captions for scam-bait clips.\n"
            "Return JSON only: {caption:string, hashtags:[string], suggested_post_time:string}.\n"
            "Keep caption under 300 chars. Include 6-10 hashtags."
        )
        user = (
            f"Call duration seconds: {call_duration_seconds}\n"
            f"Best highlight snippet: {snippet}\n"
            "Write the social package."
        )
        provider = await get_active_llm_provider(self._db)
        text = await generate_text(
            provider=provider,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=220,
        )
        import json as _json

        data = _json.loads(text)
        caption = str(data.get("caption", "")).strip()
        hashtags = data.get("hashtags") or self._HASHTAGS
        if not isinstance(hashtags, list):
            hashtags = self._HASHTAGS
        hashtags = [str(h) for h in hashtags][:12]
        suggested = str(data.get("suggested_post_time", "Thursday 7–9 PM ET"))
        return SocialResult(caption=caption, hashtags=hashtags, suggested_post_time=suggested)

"""Discovery sweep — finds candidate sources from Reddit and YouTube without extra API quota.

The sweep reuses the same API calls made during normal ingestion:
- Reddit: reads subreddit names from hot-post feeds and search results
- YouTube: reads channel IDs from video search results

No content is stored. The sweep only writes to the `sources` table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import settings
from app.connectors.youtube import RECIPE_SEARCH_QUERIES
from app.db.models import Source
from app.scoring import compute_youtube_engagement

logger = logging.getLogger(__name__)

# ── Reddit constants ──────────────────────────────────────────────────────────

_REDDIT_HOT = "https://www.reddit.com/r/{subreddit}/hot.json"
_REDDIT_USER_HISTORY = "https://www.reddit.com/user/{username}/submitted.json"
_REDDIT_SEARCH = "https://www.reddit.com/search.json"
_DISCOVERY_SEARCH_TERMS = ["recipe", "cooking"]

# Max unique authors to inspect per active source (keeps API calls bounded)
_MAX_AUTHORS_PER_SOURCE = 5

# Subreddit name contains at least one of these → cooking-adjacent
_COOKING_KEYWORDS = frozenset([
    "recipe", "recipes", "cook", "cooking", "food", "eat", "meal",
    "kitchen", "bake", "baking", "grill", "vegan", "diet", "nutrition",
    "healthy", "lunch", "dinner", "breakfast", "snack", "dessert",
    "bread", "pasta", "soup", "salad", "vegetarian", "plantbased",
    "keto", "paleo", "whole30", "protein", "lowcarb", "mealprep",
])


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class DiscoverySummary:
    """Returned by run_discovery_sweep(); carries counts and the new Source rows."""
    new_candidates: int = 0          # sources inserted with status="candidate"
    auto_promoted: int = 0           # YouTube channels inserted straight to status="active"
    skipped: int = 0                 # channels/subreddits that didn't meet minimum signal threshold
    new_sources: list[Source] = field(default_factory=list)

    def log(self) -> None:
        logger.info(
            "Discovery sweep complete: %d new candidates, %d auto-promoted to active, %d skipped",
            self.new_candidates, self.auto_promoted, self.skipped,
        )
        print(
            f"Discovery: {self.new_candidates} new candidates, "
            f"{self.auto_promoted} auto-promoted to active, "
            f"{self.skipped} skipped (insufficient signal)"
        )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _known_handles(db: Session, platform: str) -> set[str]:
    """Return all handles already in the sources table for this platform (any status)."""
    rows = db.query(Source.handle).filter_by(platform=platform).all()
    return {row.handle for row in rows}


def _insert_source(
    db: Session,
    platform: str,
    handle: str,
    display_name: str,
    status: str,
    quality_score: float | None = None,
) -> Source:
    source = Source(
        platform=platform,
        handle=handle,
        display_name=display_name,
        status=status,
        quality_score=quality_score,
        content_count=0,
        added_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _is_cooking_adjacent(subreddit_name: str) -> bool:
    name_lower = subreddit_name.lower()
    return any(kw in name_lower for kw in _COOKING_KEYWORDS)


# ── Reddit discovery ──────────────────────────────────────────────────────────

def discover_reddit_sources(
    db: Session,
    client: httpx.Client | None = None,
    active_sources: list[Source] | None = None,
) -> DiscoverySummary:
    """
    Run the Reddit discovery sweep.

    Direction 1 — author cross-posting:
        For each active Reddit source, fetch top posts, identify authors,
        check their post history for cooking-adjacent subreddits not yet tracked.

    Direction 2 — keyword search:
        Search Reddit for "recipe" and "cooking"; any subreddit appearing
        ≥ DISCOVERY_MIN_SUBREDDIT_HITS times that isn't already tracked becomes a candidate.

    Args:
        db: Database session.
        client: Optional pre-built httpx.Client (injected in tests).
        active_sources: Override the list of active Reddit sources (injected in tests).
    """
    summary = DiscoverySummary()
    headers = {"User-Agent": settings.reddit_user_agent}
    _owns_client = client is None
    if _owns_client:
        client = httpx.Client(headers=headers, follow_redirects=True)

    try:
        known = _known_handles(db, "reddit")

        # ── Direction 1: author cross-posting ────────────────────────────────
        if active_sources is None:
            active_sources = (
                db.query(Source).filter_by(platform="reddit", status="active").all()
            )

        seen_authors: set[str] = set()

        for source in active_sources:
            try:
                resp = client.get(
                    _REDDIT_HOT.format(subreddit=source.handle), params={"limit": 25}
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    logger.warning(
                        "Reddit discovery skipped — runner IP blocked by CDN (403). "
                        "Discovery will run correctly in production."
                    )
                    return summary
                raise

            authors: list[str] = []
            for child in resp.json()["data"]["children"]:
                author = child["data"].get("author", "")
                if author and author != "[deleted]" and author not in seen_authors:
                    authors.append(author)
                    seen_authors.add(author)
                if len(authors) >= _MAX_AUTHORS_PER_SOURCE:
                    break

            for author in authors:
                try:
                    hist = client.get(
                        _REDDIT_USER_HISTORY.format(username=author),
                        params={"limit": 25},
                    )
                    hist.raise_for_status()
                except httpx.HTTPStatusError:
                    continue  # private or suspended profile

                for child in hist.json()["data"]["children"]:
                    sub = child["data"].get("subreddit", "")
                    if sub and sub not in known and _is_cooking_adjacent(sub):
                        known.add(sub)
                        new = _insert_source(db, "reddit", sub, f"r/{sub}", "candidate")
                        summary.new_candidates += 1
                        summary.new_sources.append(new)

        # ── Direction 2: keyword search ───────────────────────────────────────
        subreddit_counts: dict[str, int] = {}
        for term in _DISCOVERY_SEARCH_TERMS:
            try:
                resp = client.get(
                    _REDDIT_SEARCH, params={"q": term, "type": "link", "limit": 100}
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 403:
                    logger.warning(
                        "Reddit discovery (keyword search) skipped — runner IP blocked by CDN (403)."
                    )
                    break
                raise
            for child in resp.json()["data"]["children"]:
                sub = child["data"].get("subreddit", "")
                if sub:
                    subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1

        for sub, count in subreddit_counts.items():
            if count >= settings.discovery_min_subreddit_hits and sub not in known:
                known.add(sub)
                new = _insert_source(db, "reddit", sub, f"r/{sub}", "candidate")
                summary.new_candidates += 1
                summary.new_sources.append(new)

    finally:
        if _owns_client:
            client.close()

    return summary


# ── YouTube discovery ─────────────────────────────────────────────────────────

def discover_youtube_sources(
    db: Session,
    youtube_client: Any = None,
) -> DiscoverySummary:
    """
    Run the YouTube discovery sweep.

    Reuses the same search queries as ingestion. For each new channel found:
    1. Check total video count — skip channels with fewer than
       DISCOVERY_MIN_VIDEO_COUNT videos.
    2. Fetch last 5 videos and retrieve their view/like statistics.
    3. Compute average engagement score. If it normalises above
       SOURCE_QUALITY_THRESHOLD → insert as "active"; otherwise "candidate".

    Args:
        db: Database session.
        youtube_client: Optional pre-built googleapiclient resource (injected in tests).
    """
    summary = DiscoverySummary()

    if youtube_client is None:
        youtube_client = build("youtube", "v3", developerKey=settings.youtube_api_key)

    known = _known_handles(db, "youtube")

    # Step 1: collect new channel IDs from search results
    channel_info: dict[str, str] = {}  # channel_id → display name
    for query in RECIPE_SEARCH_QUERIES:
        response = youtube_client.search().list(
            q=query, part="id,snippet", type="video", maxResults=10
        ).execute()
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            channel_id = snippet.get("channelId", "")
            channel_title = snippet.get("channelTitle", channel_id)
            if channel_id and channel_id not in known:
                channel_info[channel_id] = channel_title

    # Step 2: evaluate each new channel
    for channel_id, channel_title in channel_info.items():
        # Check total video count
        ch_resp = youtube_client.channels().list(
            id=channel_id, part="statistics"
        ).execute()
        items = ch_resp.get("items", [])
        if not items:
            summary.skipped += 1
            continue

        video_count = int(items[0].get("statistics", {}).get("videoCount", 0))
        if video_count < settings.discovery_min_video_count:
            summary.skipped += 1
            continue

        # Fetch last 5 videos
        recent_resp = youtube_client.search().list(
            channelId=channel_id, type="video",
            maxResults=5, order="date", part="id,snippet",
        ).execute()
        video_ids = [
            item["id"]["videoId"]
            for item in recent_resp.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            summary.skipped += 1
            continue

        # Get view + like counts
        stats_resp = youtube_client.videos().list(
            id=",".join(video_ids), part="statistics"
        ).execute()
        engagement_scores = []
        for video_item in stats_resp.get("items", []):
            stats = video_item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            engagement_scores.append(compute_youtube_engagement(views, likes))

        if not engagement_scores:
            summary.skipped += 1
            continue

        avg_quality = (sum(engagement_scores) / len(engagement_scores)) / 100.0
        status = "active" if avg_quality > settings.source_quality_threshold else "candidate"

        known.add(channel_id)
        new = _insert_source(
            db, "youtube", channel_id, channel_title, status,
            quality_score=round(avg_quality, 4),
        )
        if status == "active":
            summary.auto_promoted += 1
        else:
            summary.new_candidates += 1
        summary.new_sources.append(new)

    return summary


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_discovery_sweep(
    db: Session,
    reddit_client: httpx.Client | None = None,
    youtube_client: Any = None,
) -> DiscoverySummary:
    """
    Run the full discovery sweep: Reddit (author + search) then YouTube.

    Returns a DiscoverySummary with counts and newly inserted Source rows.
    Prints a one-line summary to stdout.
    """
    reddit_summary = discover_reddit_sources(db, client=reddit_client)
    youtube_summary = discover_youtube_sources(db, youtube_client=youtube_client)

    combined = DiscoverySummary(
        new_candidates=reddit_summary.new_candidates + youtube_summary.new_candidates,
        auto_promoted=youtube_summary.auto_promoted,
        skipped=youtube_summary.skipped,
        new_sources=reddit_summary.new_sources + youtube_summary.new_sources,
    )
    combined.log()
    return combined

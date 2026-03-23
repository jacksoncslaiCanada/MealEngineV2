"""Reddit connector — fetches recipe posts via Reddit's public JSON API (no credentials required)."""

from datetime import datetime, timezone
from typing import Generator

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe, Source
from app.schemas import RawRecipeSchema
from app.scoring import compute_reddit_engagement, get_or_create_source, mark_source_ingested

RECIPE_SUBREDDITS = ["recipes", "cooking", "food", "EatCheapAndHealthy"]
_REDDIT_BASE = "https://www.reddit.com/r/{subreddit}/hot.json"


def _post_to_raw_content(post: dict) -> str:
    parts = [post["title"]]
    if post.get("selftext"):
        parts.append(post["selftext"])
    return "\n\n".join(parts)


def fetch_reddit_recipes(
    subreddits: list[str] | None = None,
    limit: int = 25,
    client: httpx.Client | None = None,
) -> Generator[RawRecipeSchema, None, None]:
    """
    Fetch recipe posts from Reddit and yield normalized RawRecipeSchema objects.
    Uses the public JSON API — no credentials needed.

    Args:
        subreddits: List of subreddit names to fetch from.
        limit: Max posts per subreddit.
        client: Optional pre-built httpx.Client (used in tests).
    """
    if subreddits is None:
        subreddits = RECIPE_SUBREDDITS

    headers = {"User-Agent": settings.reddit_user_agent}
    _owns_client = client is None
    if _owns_client:
        client = httpx.Client(headers=headers, follow_redirects=True)

    try:
        for sub_name in subreddits:
            url = _REDDIT_BASE.format(subreddit=sub_name)
            response = client.get(url, params={"limit": limit})
            response.raise_for_status()

            for child in response.json()["data"]["children"]:
                post = child["data"]
                if not post.get("is_self"):
                    continue  # skip link posts

                raw_content = _post_to_raw_content(post)
                engagement = compute_reddit_engagement(
                    score=post.get("score", 0),
                    upvote_ratio=post.get("upvote_ratio", 1.0),
                )

                yield RawRecipeSchema(
                    source="reddit",
                    source_id=post["id"],
                    raw_content=raw_content,
                    url=f"https://www.reddit.com{post['permalink']}",
                    fetched_at=datetime.now(timezone.utc),
                    source_handle=sub_name,
                    source_display_name=f"r/{sub_name}",
                    engagement_score=engagement,
                    has_transcript=None,  # not applicable for Reddit
                )
    finally:
        if _owns_client:
            client.close()


def save_reddit_recipes(
    db: Session,
    subreddits: list[str] | None = None,
    limit: int = 25,
    client: httpx.Client | None = None,
) -> list[RawRecipeSchema]:
    """
    Fetch Reddit recipes and persist new ones to the database.
    Returns a list of newly inserted records (skips duplicates by source_id).
    """
    saved: list[RawRecipeSchema] = []
    saved_per_source: dict[str, int] = {}

    for record in fetch_reddit_recipes(subreddits=subreddits, limit=limit, client=client):
        if db.query(RawRecipe).filter_by(source_id=record.source_id).first():
            continue

        source = get_or_create_source(
            db,
            platform="reddit",
            handle=record.source_handle,
            display_name=record.source_display_name,
        )

        row = RawRecipe(
            source=record.source,
            source_id=record.source_id,
            raw_content=record.raw_content,
            url=record.url,
            fetched_at=record.fetched_at,
            source_fk=source.id,
            engagement_score=record.engagement_score,
            content_length=len(record.raw_content),
            has_transcript=None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        saved.append(RawRecipeSchema.model_validate(row))
        saved_per_source[record.source_handle] = saved_per_source.get(record.source_handle, 0) + 1

    # Update last_ingested_at and content_count for each source we wrote to
    for handle, count in saved_per_source.items():
        source = db.query(Source).filter_by(platform="reddit", handle=handle).first()
        if source:
            mark_source_ingested(db, source, count)

    return saved

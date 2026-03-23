"""Reddit connector — fetches recipe posts via Reddit's public JSON API (no credentials required)."""

from datetime import datetime, timezone
from typing import Generator

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe
from app.schemas import RawRecipeSchema

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
                yield RawRecipeSchema(
                    source="reddit",
                    source_id=post["id"],
                    raw_content=_post_to_raw_content(post),
                    url=f"https://www.reddit.com{post['permalink']}",
                    fetched_at=datetime.now(timezone.utc),
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

    for record in fetch_reddit_recipes(subreddits=subreddits, limit=limit, client=client):
        if db.query(RawRecipe).filter_by(source_id=record.source_id).first():
            continue

        row = RawRecipe(
            source=record.source,
            source_id=record.source_id,
            raw_content=record.raw_content,
            url=record.url,
            fetched_at=record.fetched_at,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        saved.append(RawRecipeSchema.model_validate(row))

    return saved

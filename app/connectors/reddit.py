"""Reddit connector — fetches recipe posts from specified subreddits."""

from datetime import datetime, timezone
from typing import Generator

import praw
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe
from app.schemas import RawRecipeSchema

RECIPE_SUBREDDITS = ["recipes", "cooking", "food", "EatCheapAndHealthy"]


def _build_reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )


def _post_to_raw_content(submission) -> str:
    """Combine post title and selftext into a single content string."""
    parts = [submission.title]
    if submission.selftext:
        parts.append(submission.selftext)
    return "\n\n".join(parts)


def fetch_reddit_recipes(
    subreddits: list[str] | None = None,
    limit: int = 25,
    reddit: praw.Reddit | None = None,
) -> Generator[RawRecipeSchema, None, None]:
    """
    Fetch recipe posts from Reddit and yield normalized RawRecipeSchema objects.

    Args:
        subreddits: List of subreddit names to fetch from.
        limit: Max posts per subreddit.
        reddit: Optional pre-built PRAW Reddit instance (used in tests).
    """
    if subreddits is None:
        subreddits = RECIPE_SUBREDDITS
    if reddit is None:
        reddit = _build_reddit_client()

    for sub_name in subreddits:
        subreddit = reddit.subreddit(sub_name)
        for submission in subreddit.hot(limit=limit):
            if submission.is_self:  # only text posts (recipes live in self-posts)
                yield RawRecipeSchema(
                    source="reddit",
                    source_id=submission.id,
                    raw_content=_post_to_raw_content(submission),
                    url=f"https://www.reddit.com{submission.permalink}",
                    fetched_at=datetime.now(timezone.utc),
                )


def save_reddit_recipes(
    db: Session,
    subreddits: list[str] | None = None,
    limit: int = 25,
    reddit: praw.Reddit | None = None,
) -> list[RawRecipeSchema]:
    """
    Fetch Reddit recipes and persist new ones to the database.

    Returns a list of newly inserted records (skips duplicates by source_id).
    """
    saved: list[RawRecipeSchema] = []

    for record in fetch_reddit_recipes(subreddits=subreddits, limit=limit, reddit=reddit):
        exists = db.query(RawRecipe).filter_by(source_id=record.source_id).first()
        if exists:
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

"""RSS connector — fetches recipes from food blog RSS feeds."""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
from sqlalchemy.orm import Session

from app.db.models import RawRecipe, Source
from app.schemas import RawRecipeSchema
from app.scoring import get_or_create_source, mark_source_ingested

WOKS_OF_LIFE_FEED = "https://thewoksoflife.com/feed/"
RSS_FEEDS = [WOKS_OF_LIFE_FEED]


def _entry_id(entry) -> str:
    """Stable unique ID: use entry.id if present, else hash the link."""
    if getattr(entry, "id", None):
        return entry.id
    link = getattr(entry, "link", "") or ""
    return hashlib.sha256(link.encode()).hexdigest()[:16]


def _entry_content(entry) -> str:
    """Return best available text content from an RSS entry."""
    if getattr(entry, "content", None):
        return entry.content[0].get("value", "")
    return getattr(entry, "summary", "") or ""


def _build_raw_content(entry) -> str:
    title = getattr(entry, "title", "") or ""
    content = _entry_content(entry)
    parts = [f"Title: {title}"]
    if content:
        parts.append(f"Content: {content}")
    return "\n\n".join(parts)


def _feed_handle(feed_url: str) -> str:
    """Derive a short handle from the feed URL (domain without www.)."""
    try:
        host = urlparse(feed_url).hostname or feed_url
        return host.removeprefix("www.")
    except Exception:
        return feed_url


def fetch_rss_recipes(
    feed_urls: list[str] | None = None,
    max_results: int = 20,
) -> list[RawRecipeSchema]:
    """
    Fetch entries from RSS feeds and return normalized RawRecipeSchema objects.

    Args:
        feed_urls: List of RSS feed URLs to fetch. Defaults to RSS_FEEDS.
        max_results: Max entries to take per feed.
    """
    if feed_urls is None:
        feed_urls = RSS_FEEDS

    records: list[RawRecipeSchema] = []
    for feed_url in feed_urls:
        parsed = feedparser.parse(feed_url)
        handle = _feed_handle(feed_url)
        feed_title = getattr(parsed.feed, "title", None) or handle

        for entry in parsed.entries[:max_results]:
            raw_content = _build_raw_content(entry)
            # Engagement proxy: content length in hundreds of chars, capped at 80
            engagement = min(len(raw_content) / 100.0, 80.0)

            records.append(
                RawRecipeSchema(
                    source="rss",
                    source_id=_entry_id(entry),
                    raw_content=raw_content,
                    url=getattr(entry, "link", "") or "",
                    fetched_at=datetime.now(timezone.utc),
                    source_handle=handle,
                    source_display_name=feed_title,
                    engagement_score=engagement,
                    has_transcript=False,
                )
            )

    return records


def save_rss_recipes(
    db: Session,
    feed_urls: list[str] | None = None,
    max_results: int = 20,
) -> list[RawRecipeSchema]:
    """
    Fetch RSS recipes and persist new ones to the database.

    Returns a list of newly inserted records (skips duplicates by source_id).
    """
    records = fetch_rss_recipes(feed_urls=feed_urls, max_results=max_results)

    saved: list[RawRecipeSchema] = []
    saved_per_source: dict[str, int] = {}

    for record in records:
        if db.query(RawRecipe).filter_by(source_id=record.source_id).first():
            continue

        source = get_or_create_source(
            db,
            platform="rss",
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
            has_transcript=record.has_transcript,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        saved.append(RawRecipeSchema.model_validate(row))
        saved_per_source[record.source_handle] = saved_per_source.get(record.source_handle, 0) + 1

    for handle, count in saved_per_source.items():
        source = db.query(Source).filter_by(platform="rss", handle=handle).first()
        if source:
            mark_source_ingested(db, source, count)

    return saved

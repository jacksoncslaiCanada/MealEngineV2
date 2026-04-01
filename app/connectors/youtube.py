"""YouTube connector — fetches recipe video metadata and transcripts."""

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe, Source
from app.schemas import RawRecipeSchema
from app.scoring import compute_youtube_engagement, get_or_create_source, mark_source_ingested

RECIPE_SEARCH_QUERIES = ["homemade recipe", "how to cook", "easy dinner recipe", "maangchi korean recipe"]


def _build_youtube_client(api_key: str | None = None):
    return build("youtube", "v3", developerKey=api_key or settings.youtube_api_key)


def _fetch_transcript(video_id: str) -> str:
    """Return the transcript text for a video, or empty string if unavailable."""
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(e["text"] for e in entries)
    except (TranscriptsDisabled, NoTranscriptFound):
        return ""


def _build_raw_content(title: str, description: str, transcript: str) -> str:
    parts = [f"Title: {title}"]
    if description:
        parts.append(f"Description: {description}")
    if transcript:
        parts.append(f"Transcript: {transcript}")
    return "\n\n".join(parts)


_YT_STATS_BATCH_SIZE = 50


def _fetch_statistics(youtube_client, video_ids: list[str]) -> dict[str, tuple[int, int]]:
    """Batch-fetch view and like counts for a list of video IDs.

    Chunks requests to stay within the YouTube API limit of 50 IDs per call.
    Returns a dict mapping video_id -> (views, likes).
    """
    if not video_ids:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for i in range(0, len(video_ids), _YT_STATS_BATCH_SIZE):
        batch = video_ids[i : i + _YT_STATS_BATCH_SIZE]
        response = youtube_client.videos().list(
            part="statistics",
            id=",".join(batch),
        ).execute()
        for item in response.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            result[vid] = (views, likes)
    return result


def fetch_youtube_recipes(
    queries: list[str] | None = None,
    max_results: int = 10,
    youtube_client: Any = None,
    transcript_fetcher=None,
    stats_fetcher=None,
) -> list[RawRecipeSchema]:
    """
    Search YouTube for recipe videos and return normalized RawRecipeSchema objects.

    Args:
        queries: Search queries to run.
        max_results: Max results per query.
        youtube_client: Optional pre-built client (used in tests).
        transcript_fetcher: Optional callable(video_id) -> str (used in tests).
        stats_fetcher: Optional callable(video_ids) -> dict[str, tuple[int, int]] (used in tests).
    """
    if queries is None:
        queries = RECIPE_SEARCH_QUERIES
    if youtube_client is None:
        youtube_client = _build_youtube_client()
    if transcript_fetcher is None:
        transcript_fetcher = _fetch_transcript
    if stats_fetcher is None:
        stats_fetcher = lambda ids: _fetch_statistics(youtube_client, ids)

    seen: set[str] = set()
    # Collect raw data before stats so we can batch the statistics call
    intermediate: list[dict] = []

    for query in queries:
        response = youtube_client.search().list(
            q=query,
            part="id,snippet",
            type="video",
            maxResults=max_results,
        ).execute()

        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            if video_id in seen:
                continue
            seen.add(video_id)

            snippet = item["snippet"]
            intermediate.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", snippet.get("channelId", "")),
                "transcript": transcript_fetcher(video_id),
            })

    # Batch-fetch statistics for all collected video IDs in one API call
    stats = stats_fetcher(list(seen))

    records: list[RawRecipeSchema] = []
    for data in intermediate:
        views_likes = stats.get(data["video_id"])
        if views_likes is not None:
            views, likes = views_likes
            engagement = compute_youtube_engagement(views, likes)
        else:
            engagement = None

        raw_content = _build_raw_content(data["title"], data["description"], data["transcript"])
        records.append(
            RawRecipeSchema(
                source="youtube",
                source_id=data["video_id"],
                raw_content=raw_content,
                url=f"https://www.youtube.com/watch?v={data['video_id']}",
                fetched_at=datetime.now(timezone.utc),
                source_handle=data["channel_id"],
                source_display_name=data["channel_title"],
                engagement_score=engagement,
                has_transcript=bool(data["transcript"]),
            )
        )

    return records


def save_youtube_recipes(
    db: Session,
    queries: list[str] | None = None,
    max_results: int = 10,
    youtube_client: Any = None,
    transcript_fetcher=None,
    stats_fetcher=None,
) -> list[RawRecipeSchema]:
    """
    Fetch YouTube recipes and persist new ones to the database.

    Returns a list of newly inserted records (skips duplicates by source_id).
    """
    records = fetch_youtube_recipes(
        queries=queries,
        max_results=max_results,
        youtube_client=youtube_client,
        transcript_fetcher=transcript_fetcher,
        stats_fetcher=stats_fetcher,
    )

    saved: list[RawRecipeSchema] = []
    saved_per_source: dict[str, int] = {}

    for record in records:
        if db.query(RawRecipe).filter_by(source_id=record.source_id).first():
            continue

        source_fk = None
        if record.source_handle:
            source = get_or_create_source(
                db,
                platform="youtube",
                handle=record.source_handle,
                display_name=record.source_display_name,
            )
            source_fk = source.id
            saved_per_source[record.source_handle] = (
                saved_per_source.get(record.source_handle, 0) + 1
            )

        row = RawRecipe(
            source=record.source,
            source_id=record.source_id,
            raw_content=record.raw_content,
            url=record.url,
            fetched_at=record.fetched_at,
            source_fk=source_fk,
            engagement_score=record.engagement_score,
            content_length=len(record.raw_content),
            has_transcript=record.has_transcript,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        saved.append(RawRecipeSchema.model_validate(row))

    # Update last_ingested_at and content_count for each channel we wrote to
    for handle, count in saved_per_source.items():
        source = db.query(Source).filter_by(platform="youtube", handle=handle).first()
        if source:
            mark_source_ingested(db, source, count)

    return saved

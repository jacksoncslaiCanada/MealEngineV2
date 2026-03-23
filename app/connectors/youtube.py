"""YouTube connector — fetches recipe video metadata and transcripts."""

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe
from app.schemas import RawRecipeSchema

RECIPE_SEARCH_QUERIES = ["recipe", "how to cook", "easy dinner recipe"]


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


def fetch_youtube_recipes(
    queries: list[str] | None = None,
    max_results: int = 10,
    youtube_client: Any = None,
    transcript_fetcher=None,
) -> list[RawRecipeSchema]:
    """
    Search YouTube for recipe videos and return normalized RawRecipeSchema objects.

    Args:
        queries: Search queries to run.
        max_results: Max results per query.
        youtube_client: Optional pre-built client (used in tests).
        transcript_fetcher: Optional callable(video_id) -> str (used in tests).
    """
    if queries is None:
        queries = RECIPE_SEARCH_QUERIES
    if youtube_client is None:
        youtube_client = _build_youtube_client()
    if transcript_fetcher is None:
        transcript_fetcher = _fetch_transcript

    seen: set[str] = set()
    records: list[RawRecipeSchema] = []

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
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            transcript = transcript_fetcher(video_id)

            records.append(
                RawRecipeSchema(
                    source="youtube",
                    source_id=video_id,
                    raw_content=_build_raw_content(title, description, transcript),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    fetched_at=datetime.now(timezone.utc),
                )
            )

    return records


def save_youtube_recipes(
    db: Session,
    queries: list[str] | None = None,
    max_results: int = 10,
    youtube_client: Any = None,
    transcript_fetcher=None,
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
    )

    saved: list[RawRecipeSchema] = []
    for record in records:
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

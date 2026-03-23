from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, field_validator


class RawRecipeSchema(BaseModel):
    source: Literal["reddit", "youtube"]
    source_id: str
    raw_content: str
    url: str
    fetched_at: datetime

    # Source registry — populated by connectors to link recipes to their source
    source_handle: str | None = None        # subreddit name or YouTube channel ID
    source_display_name: str | None = None  # human-readable label for the source

    # Engagement signals — captured at fetch time, None if unavailable
    engagement_score: float | None = None   # 0–100 normalised score
    has_transcript: bool | None = None      # YouTube only

    model_config = {"from_attributes": True}

    @field_validator("fetched_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v):
        """SQLite strips tzinfo on read-back; treat all naive datetimes as UTC."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class SourceSchema(BaseModel):
    id: int
    platform: str
    handle: str
    display_name: str
    status: str
    quality_score: float | None
    content_count: int
    added_at: datetime
    last_ingested_at: datetime | None

    model_config = {"from_attributes": True}

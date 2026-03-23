from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, field_validator


class RawRecipeSchema(BaseModel):
    source: Literal["reddit", "youtube"]
    source_id: str
    raw_content: str
    url: str
    fetched_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("fetched_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v):
        """SQLite strips tzinfo on read-back; treat all naive datetimes as UTC."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

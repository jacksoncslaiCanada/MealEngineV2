from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class RawRecipe(Base):
    """Raw recipe record as fetched from the source."""

    __tablename__ = "raw_recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32))       # "reddit" | "youtube"
    source_id: Mapped[str] = mapped_column(String(128), unique=True)
    raw_content: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

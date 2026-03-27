from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Float, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Source(Base):
    """A tracked recipe source — a subreddit or a YouTube channel."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(16))        # "reddit" | "youtube"
    handle: Mapped[str] = mapped_column(String(256))         # subreddit name or YouTube channel ID
    display_name: Mapped[str] = mapped_column(String(256))   # human-readable label
    status: Mapped[str] = mapped_column(String(16), default="active")
    # "candidate" | "active" | "paused" | "rejected"
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_count: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    recipes: Mapped[list["RawRecipe"]] = relationship("RawRecipe", back_populates="source_ref")

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("platform", "handle", name="uq_source_platform_handle"),
    )


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

    # Source registry linkage
    source_fk: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=True
    )
    source_ref: Mapped["Source | None"] = relationship("Source", back_populates="recipes")

    # Engagement signals captured at fetch time
    engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_transcript: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    ingredients: Mapped[list["Ingredient"]] = relationship("Ingredient", back_populates="recipe")


class Ingredient(Base):
    """A single structured ingredient extracted from a raw recipe by Claude."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_name: Mapped[str] = mapped_column(String(256))
    quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # FK back to the raw recipe this ingredient was extracted from
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_recipes.id"), nullable=False)
    recipe: Mapped["RawRecipe"] = relationship("RawRecipe", back_populates="ingredients")

    # Denormalized source FK — useful for querying all ingredients by platform
    # without joining through raw_recipes
    source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=True
    )

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

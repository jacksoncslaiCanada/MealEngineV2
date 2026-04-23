from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Float, Integer, Boolean, ForeignKey, LargeBinary
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
        Integer, ForeignKey("sources.id"), nullable=True, index=True
    )
    source_ref: Mapped["Source | None"] = relationship("Source", back_populates="recipes")

    # Engagement signals captured at fetch time
    engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_transcript: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Claude classification (set by classifier.py)
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)   # easy|medium|complex
    cuisine: Mapped[str | None] = mapped_column(String(64), nullable=True)      # e.g. Asian, Italian
    meal_type: Mapped[str | None] = mapped_column(String(16), nullable=True)    # breakfast|lunch|dinner|any
    quick_steps: Mapped[str | None] = mapped_column(Text, nullable=True)        # JSON: 3-step method
    prep_time: Mapped[int | None] = mapped_column(Integer, nullable=True)       # total minutes
    dietary_tags: Mapped[str | None] = mapped_column(Text, nullable=True)       # JSON: list of tags
    spice_level: Mapped[str | None] = mapped_column(String(16), nullable=True)  # mild|medium|hot
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)        # number of servings
    card_steps: Mapped[str | None] = mapped_column(Text, nullable=True)         # JSON: 5-6 detailed steps for recipe card
    card_tip: Mapped[str | None] = mapped_column(Text, nullable=True)           # chef's tip for recipe card
    card_summary: Mapped[str | None] = mapped_column(Text, nullable=True)       # 2-3 sentence enticing headnote for recipe card
    card_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)     # resolved image URL (thumbnail or Flux-generated)
    card_title: Mapped[str | None] = mapped_column(Text, nullable=True)         # AI-generated clean dish name for recipe card

    ingredients: Mapped[list["Ingredient"]] = relationship("Ingredient", back_populates="recipe")


class Ingredient(Base):
    """A single structured ingredient extracted from a raw recipe by Claude."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ingredient_name: Mapped[str] = mapped_column(String(256))
    canonical_name: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # FK back to the raw recipe this ingredient was extracted from
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_recipes.id"), nullable=False, index=True)
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


class Subscriber(Base):
    """A buyer who receives weekly meal plan PDFs by email."""

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False)       # little_ones | teen_table | etc.
    plans_remaining: Mapped[int] = mapped_column(Integer, default=4)       # counts down from 4
    gumroad_order_id: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class RecipeComponent(Base):
    """A named meal component (base/flavor/protein) — powers the Blueprint card view."""

    __tablename__ = "recipe_components"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("raw_recipes.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16))       # "base" | "flavor" | "protein" | "other"
    label: Mapped[str] = mapped_column(String(256))     # e.g. "Honey Garlic Glaze", "Jasmine Rice"
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped["RawRecipe"] = relationship("RawRecipe")


class MealPlan(Base):
    """A generated 7-day meal plan with PDF."""

    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    variant: Mapped[str] = mapped_column(String(32))          # weeknight_easy|family_variety|asian_kitchen|weekend_cook
    week_label: Mapped[str] = mapped_column(String(16))       # e.g. "2024-W15"
    plan_json: Mapped[str] = mapped_column(Text)              # JSON: 7-day schedule
    shopping_json: Mapped[str] = mapped_column(Text)          # JSON: aggregated shopping list
    pdf_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

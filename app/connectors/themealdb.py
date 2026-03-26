"""TheMealDB connector — fetches recipe data via the free public API (no credentials required)."""

from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.db.models import RawRecipe, Source
from app.schemas import RawRecipeSchema
from app.scoring import compute_themealdb_completeness, get_or_create_source, mark_source_ingested

RECIPE_SEARCH_QUERIES = ["chicken", "pasta", "beef", "salmon"]
_THEMEALDB_BASE = "https://www.themealdb.com/api/json/v1/1/search.php"


def _count_ingredients(meal: dict) -> int:
    """Count non-empty ingredient slots (1–20)."""
    return sum(
        1 for i in range(1, 21)
        if (meal.get(f"strIngredient{i}") or "").strip()
    )


def _build_ingredients(meal: dict) -> str:
    """Extract ingredient/measure pairs into a readable list."""
    lines = []
    for i in range(1, 21):
        ingredient = (meal.get(f"strIngredient{i}") or "").strip()
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        if ingredient:
            lines.append(f"- {measure} {ingredient}".strip())
    return "\n".join(lines)


def _build_raw_content(meal: dict) -> str:
    parts = [f"Meal: {meal['strMeal']}"]
    if meal.get("strCategory"):
        parts.append(f"Category: {meal['strCategory']}")
    if meal.get("strArea"):
        parts.append(f"Cuisine: {meal['strArea']}")
    ingredients = _build_ingredients(meal)
    if ingredients:
        parts.append(f"Ingredients:\n{ingredients}")
    if meal.get("strInstructions"):
        parts.append(f"Instructions:\n{meal['strInstructions'].strip()}")
    return "\n\n".join(parts)


def fetch_themealdb_recipes(
    queries: list[str] | None = None,
    max_results: int = 10,
    client: httpx.Client | None = None,
) -> list[RawRecipeSchema]:
    """
    Search TheMealDB for recipe meals and return normalized RawRecipeSchema objects.

    Uses the free public API — no credentials needed.

    Args:
        queries: Search terms to run against the meal name endpoint.
        max_results: Max total results to return across all queries.
        client: Optional pre-built httpx.Client (used in tests).
    """
    if queries is None:
        queries = RECIPE_SEARCH_QUERIES

    _owns_client = client is None
    if _owns_client:
        client = httpx.Client(follow_redirects=True)

    seen: set[str] = set()
    records: list[RawRecipeSchema] = []

    try:
        for query in queries:
            if len(records) >= max_results:
                break

            response = client.get(_THEMEALDB_BASE, params={"s": query})
            response.raise_for_status()

            meals = response.json().get("meals") or []
            for meal in meals:
                if len(records) >= max_results:
                    break

                meal_id = meal["idMeal"]
                if meal_id in seen:
                    continue
                seen.add(meal_id)

                category = meal.get("strCategory") or "other"
                ingredient_count = _count_ingredients(meal)
                instruction_length = len((meal.get("strInstructions") or "").strip())
                completeness = compute_themealdb_completeness(ingredient_count, instruction_length)

                records.append(
                    RawRecipeSchema(
                        source="themealdb",
                        source_id=meal_id,
                        raw_content=_build_raw_content(meal),
                        url=f"https://www.themealdb.com/meal/{meal_id}",
                        fetched_at=datetime.now(timezone.utc),
                        source_handle=category.lower(),
                        source_display_name=category,
                        engagement_score=completeness,
                        has_transcript=None,
                    )
                )
    finally:
        if _owns_client:
            client.close()

    return records


def save_themealdb_recipes(
    db: Session,
    queries: list[str] | None = None,
    max_results: int = 10,
    client: httpx.Client | None = None,
) -> list[RawRecipeSchema]:
    """
    Fetch TheMealDB recipes and persist new ones to the database.

    Returns a list of newly inserted records (skips duplicates by source_id).
    """
    records = fetch_themealdb_recipes(queries=queries, max_results=max_results, client=client)

    saved: list[RawRecipeSchema] = []
    saved_per_source: dict[str, int] = {}

    for record in records:
        if db.query(RawRecipe).filter_by(source_id=record.source_id).first():
            continue

        source = get_or_create_source(
            db,
            platform="themealdb",
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
            has_transcript=None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        saved.append(RawRecipeSchema.model_validate(row))
        saved_per_source[record.source_handle] = saved_per_source.get(record.source_handle, 0) + 1

    for handle, count in saved_per_source.items():
        source = db.query(Source).filter_by(platform="themealdb", handle=handle).first()
        if source:
            mark_source_ingested(db, source, count)

    return saved

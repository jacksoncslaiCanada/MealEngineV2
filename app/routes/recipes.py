"""Recipe endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import Ingredient, RawRecipe
from app.db.session import get_db
from app.normaliser import normalise_ingredient
from sqlalchemy import func

from app.routes.schemas import IngredientOut, IngredientSearchResult, MealPlanResult, RecipeBrowseItem, RecipeDetailOut, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/stats", response_model=dict[str, int])
def recipe_stats(db: Session = Depends(get_db)) -> dict[str, int]:
    """Return total recipe count per source platform."""
    rows = (
        db.query(RawRecipe.source, func.count(RawRecipe.id))
        .group_by(RawRecipe.source)
        .all()
    )
    return {source: count for source, count in rows}


def _recipe_ids_for_term(db: Session, term: str) -> set[int]:
    """Return the set of recipe IDs that have at least one ingredient matching term."""
    canonical = normalise_ingredient(term)
    rows = (
        db.query(Ingredient.recipe_id)
        .filter(
            or_(
                Ingredient.ingredient_name.ilike(f"%{term}%"),
                Ingredient.canonical_name.ilike(f"%{canonical}%"),
            )
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


@router.get("/meal-plan", response_model=list[MealPlanResult])
def meal_plan(
    ingredient: list[str] = Query(
        ...,
        min_length=1,
        description="Ingredients you have on hand. Repeat for each item (e.g. ?ingredient=chicken&ingredient=garlic).",
    ),
    min_coverage: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
        description="Minimum fraction of recipe ingredients that must be covered (0.0–1.0). Default 0.5.",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[MealPlanResult]:
    """Find recipes you can make from your pantry.

    Pass each ingredient you have as a separate `ingredient` parameter.
    Returns recipes sorted by coverage (highest first) — the fraction of
    the recipe's ingredients that are covered by your pantry.

    Use `min_coverage=1.0` to see only recipes where you have every ingredient.
    Use `min_coverage=0.0` to include all recipes that use at least one pantry item.
    """
    pantry_raw = [t.strip().lower() for t in ingredient if t.strip()]
    if not pantry_raw:
        return []

    # Build normalised pantry set for matching against canonical_name
    pantry_canonical = {normalise_ingredient(t) for t in pantry_raw}

    # Pre-filter: candidate recipes must share at least one ingredient with pantry
    candidate_ids: set[int] = set()
    for term in pantry_raw:
        candidate_ids |= _recipe_ids_for_term(db, term)

    if not candidate_ids:
        return []

    # Load candidate recipes with all their ingredients
    recipes = (
        db.query(RawRecipe)
        .options(joinedload(RawRecipe.ingredients))
        .filter(RawRecipe.id.in_(candidate_ids))
        .all()
    )

    # Score each recipe by coverage
    scored: list[tuple[float, int, int, RawRecipe]] = []
    for recipe in recipes:
        if not recipe.ingredients:
            continue
        matched = sum(
            1 for ing in recipe.ingredients
            if _ingredient_in_pantry(ing, pantry_raw, pantry_canonical)
        )
        total = len(recipe.ingredients)
        coverage = matched / total
        if coverage >= min_coverage:
            scored.append((coverage, matched, total, recipe))

    # Sort by coverage desc, then engagement_score desc as tiebreaker
    scored.sort(key=lambda x: (x[0], x[3].engagement_score or 0.0), reverse=True)

    # Apply offset + limit
    page = scored[offset: offset + limit]

    return [
        MealPlanResult(
            **RecipeDetailOut.model_validate(recipe).model_dump(),
            coverage=round(coverage, 4),
            matched_count=matched,
            total_count=total,
        )
        for coverage, matched, total, recipe in page
    ]


def _ingredient_in_pantry(
    ing: Ingredient,
    pantry_raw: list[str],
    pantry_canonical: set[str],
) -> bool:
    """Return True if this ingredient is covered by any pantry item."""
    ing_name = ing.ingredient_name.lower()
    ing_canonical = ing.canonical_name.lower() if ing.canonical_name else None
    for term in pantry_raw:
        if term in ing_name or ing_name in term:
            return True
    if ing_canonical:
        for canon in pantry_canonical:
            if canon in ing_canonical or ing_canonical in canon:
                return True
    return False


@router.get("/search", response_model=list[RecipeDetailOut])
def search_recipes(
    ingredient: list[str] = Query(
        ...,
        min_length=1,
        description="Ingredient(s) to search for. Repeat to add more (e.g. ?ingredient=chicken&ingredient=garlic).",
    ),
    match: Literal["all", "any"] = Query(
        "all",
        description="'all' — recipe must contain every ingredient (AND). 'any' — at least one (OR).",
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RecipeDetailOut]:
    """Search for recipes by one or more ingredients.

    Pass `ingredient` once per term. Use `match=all` (default) to require every
    ingredient to be present, or `match=any` to return recipes that contain at
    least one of them.
    """
    terms = [t.strip().lower() for t in ingredient if t.strip()]
    if not terms:
        return []

    if match == "all":
        matching_ids: set[int] | None = None
        for term in terms:
            ids = _recipe_ids_for_term(db, term)
            matching_ids = ids if matching_ids is None else matching_ids & ids
            if not matching_ids:
                return []
    else:  # "any"
        matching_ids = set()
        for term in terms:
            matching_ids |= _recipe_ids_for_term(db, term)

    if not matching_ids:
        return []

    recipes = (
        db.query(RawRecipe)
        .options(joinedload(RawRecipe.ingredients))
        .filter(RawRecipe.id.in_(matching_ids))
        .order_by(RawRecipe.engagement_score.desc().nullslast())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [RecipeDetailOut.model_validate(r) for r in recipes]


def _extract_title(raw_content: str) -> str:
    """Pull a human-readable title from the first line of raw_content."""
    first = (raw_content or "").split("\n")[0]
    for prefix in ("Title: ", "Meal: "):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return first.strip()[:120]


@router.get("/browse", response_model=list[RecipeBrowseItem])
def browse_recipes(
    q: str | None = Query(None, description="Keyword search in recipe title / content"),
    source: str | None = Query(None, description="Filter by source platform (youtube, themealdb, rss, reddit)"),
    min_ingredients: int = Query(0, ge=0, description="Minimum extracted ingredient count"),
    sort: Literal["newest", "engagement"] = Query("newest", description="Sort order"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RecipeBrowseItem]:
    """Browse all recipes with lightweight metadata, filtering and sorting.

    Designed for the Recipe Browser UI — returns title, source, ingredient count,
    and engagement score without loading full raw content or ingredient lists.
    """
    # Correlated subquery: count of extracted ingredients per recipe
    ing_count_sq = (
        db.query(func.count(Ingredient.id))
        .filter(Ingredient.recipe_id == RawRecipe.id)
        .correlate(RawRecipe)
        .scalar_subquery()
    )

    query = db.query(RawRecipe, ing_count_sq.label("ing_count"))

    if source:
        query = query.filter(RawRecipe.source == source)
    if q:
        query = query.filter(RawRecipe.raw_content.ilike(f"%{q}%"))
    if min_ingredients > 0:
        query = query.having(ing_count_sq >= min_ingredients)

    if sort == "engagement":
        query = query.order_by(RawRecipe.engagement_score.desc().nullslast())
    else:
        query = query.order_by(RawRecipe.fetched_at.desc())

    rows = query.offset(offset).limit(limit).all()

    return [
        RecipeBrowseItem(
            id=recipe.id,
            source=recipe.source,
            url=recipe.url,
            title=_extract_title(recipe.raw_content),
            ingredient_count=ing_count,
            engagement_score=recipe.engagement_score,
            fetched_at=recipe.fetched_at,
        )
        for recipe, ing_count in rows
    ]


@router.get("", response_model=list[RecipeOut])
def list_recipes(
    source: str | None = Query(None, description="Filter by source platform (e.g. 'themealdb', 'youtube')"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RecipeOut]:
    """List recipes, optionally filtered by source platform."""
    q = db.query(RawRecipe)
    if source:
        q = q.filter(RawRecipe.source == source)
    rows = q.order_by(RawRecipe.fetched_at.desc()).offset(offset).limit(limit).all()
    return [RecipeOut.model_validate(r) for r in rows]


@router.get("/{recipe_id}", response_model=RecipeDetailOut)
def get_recipe(recipe_id: int, db: Session = Depends(get_db)) -> RecipeDetailOut:
    """Get a single recipe with its extracted ingredients."""
    recipe = (
        db.query(RawRecipe)
        .options(joinedload(RawRecipe.ingredients))
        .filter(RawRecipe.id == recipe_id)
        .first()
    )
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found")
    return RecipeDetailOut.model_validate(recipe)


@router.get("/{recipe_id}/ingredients", response_model=list[IngredientOut])
def get_recipe_ingredients(recipe_id: int, db: Session = Depends(get_db)) -> list[IngredientOut]:
    """Get the structured ingredient list for a single recipe."""
    recipe = db.query(RawRecipe).filter(RawRecipe.id == recipe_id).first()
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found")

    rows = (
        db.query(Ingredient)
        .filter(Ingredient.recipe_id == recipe_id)
        .order_by(Ingredient.id)
        .all()
    )
    return [IngredientOut.model_validate(r) for r in rows]

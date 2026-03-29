"""Recipe endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import Ingredient, RawRecipe
from app.db.session import get_db
from app.normaliser import normalise_ingredient
from app.routes.schemas import IngredientOut, IngredientSearchResult, RecipeDetailOut, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


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

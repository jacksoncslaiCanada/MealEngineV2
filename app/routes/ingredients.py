"""Ingredient endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Ingredient, RawRecipe
from app.db.session import get_db
from app.normaliser import normalise_ingredient
from app.routes.schemas import IngredientSearchResult

router = APIRouter(prefix="/ingredients", tags=["ingredients"])


@router.get("/search", response_model=list[IngredientSearchResult])
def search_ingredients(
    name: str = Query(..., min_length=1, description="Ingredient name to search for (case-insensitive substring match)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[IngredientSearchResult]:
    """Find recipes that contain an ingredient matching the search term.

    Matches against both the raw ingredient_name and the canonical_name,
    so searching "chicken" also returns rows where canonical_name="chicken"
    even if ingredient_name is "chicken thighs" or "chicken breast".
    """
    canonical = normalise_ingredient(name)
    rows = (
        db.query(Ingredient, RawRecipe)
        .join(RawRecipe, Ingredient.recipe_id == RawRecipe.id)
        .filter(
            or_(
                Ingredient.ingredient_name.ilike(f"%{name}%"),
                Ingredient.canonical_name.ilike(f"%{canonical}%"),
            )
        )
        .order_by(Ingredient.canonical_name, Ingredient.ingredient_name, RawRecipe.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        IngredientSearchResult(
            ingredient_name=ing.ingredient_name,
            canonical_name=ing.canonical_name,
            recipe_id=recipe.id,
            recipe_source=recipe.source,
            recipe_url=recipe.url,
            quantity=ing.quantity,
            unit=ing.unit,
        )
        for ing, recipe in rows
    ]

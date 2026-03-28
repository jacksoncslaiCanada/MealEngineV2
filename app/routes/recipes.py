"""Recipe endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.models import Ingredient, RawRecipe
from app.db.session import get_db
from app.routes.schemas import IngredientOut, IngredientSearchResult, RecipeDetailOut, RecipeOut

router = APIRouter(prefix="/recipes", tags=["recipes"])


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

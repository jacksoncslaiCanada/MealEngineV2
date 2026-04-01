"""Pydantic response schemas for the API layer.

Kept separate from app/schemas.py (which holds ingest-layer schemas) to avoid
coupling the public API contract to internal pipeline data shapes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ingredient_name: str
    canonical_name: Optional[str]
    quantity: Optional[str]
    unit: Optional[str]
    extracted_at: datetime


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    url: str
    fetched_at: datetime
    engagement_score: Optional[float]
    content_length: Optional[int]
    has_transcript: Optional[bool]


class RecipeDetailOut(RecipeOut):
    """Recipe with its extracted ingredients embedded."""
    ingredients: list[IngredientOut]


class IngredientSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredient_name: str
    canonical_name: Optional[str]
    recipe_id: int
    recipe_source: str
    recipe_url: str
    quantity: Optional[str]
    unit: Optional[str]


class MealPlanResult(RecipeDetailOut):
    """Recipe with pantry coverage metrics."""
    coverage: float       # 0.0–1.0 — fraction of recipe ingredients covered by the pantry
    matched_count: int    # number of recipe ingredients matched
    total_count: int      # total extracted ingredients in the recipe


class RecipeBrowseItem(BaseModel):
    """Lightweight recipe row for the Recipe Browser UI."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    title: str
    ingredient_count: int
    engagement_score: Optional[float]
    fetched_at: datetime

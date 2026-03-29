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

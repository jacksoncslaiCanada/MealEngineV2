"""Recipe classifier.

Uses Claude tool-use to label each RawRecipe with:
  - difficulty  : "easy" | "medium" | "complex"
  - cuisine     : e.g. "Asian", "Italian", "American", "Mexican", ...
  - meal_type   : "breakfast" | "lunch" | "dinner" | "any"
  - quick_steps : JSON list of 3 short cooking-method bullet strings

Classification is skipped for recipes that already have all four fields set.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

_CLASSIFY_TOOL: anthropic.types.ToolParam = {
    "name": "classify_recipe",
    "description": (
        "Classify a recipe by difficulty, cuisine, meal type, "
        "and summarise the cooking method in 3 short steps."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "complex"],
                "description": (
                    "easy = under 30 min, minimal skill; "
                    "medium = 30-60 min or moderate technique; "
                    "complex = over 60 min or advanced skill"
                ),
            },
            "cuisine": {
                "type": "string",
                "enum": [
                    "Asian", "Italian", "American", "Mexican",
                    "Mediterranean", "Indian", "French", "Other",
                ],
                "description": "Primary cuisine style of the recipe.",
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "any"],
                "description": (
                    "Most appropriate meal slot. Use 'any' if the recipe "
                    "fits multiple slots equally (e.g. a salad)."
                ),
            },
            "quick_steps": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
                "description": (
                    "Exactly 3 short bullet strings summarising the cooking method. "
                    "Each under 12 words. Example: "
                    '["Marinate chicken 30 min.", '
                    '"Stir-fry on high heat 8 min.", '
                    '"Add sauce, reduce 2 min."]'
                ),
            },
        },
        "required": ["difficulty", "cuisine", "meal_type", "quick_steps"],
    },
}

_SYSTEM = (
    "You are a culinary classification assistant. "
    "Given a recipe, call classify_recipe with the correct labels and a 3-step method summary."
)


# ---------------------------------------------------------------------------
# Single-recipe classification
# ---------------------------------------------------------------------------

def classify_recipe(
    db: Session,
    recipe: RawRecipe,
    *,
    client: Optional[anthropic.Anthropic] = None,
) -> RawRecipe:
    """Classify a single recipe and persist the labels. Returns the recipe."""
    if recipe.difficulty and recipe.cuisine and recipe.meal_type and recipe.quick_steps:
        return recipe  # already done

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Use first 1000 chars — enough for steps, saves tokens
    snippet = recipe.raw_content[:1000]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM,
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_recipe"},
        messages=[{"role": "user", "content": f"Classify this recipe:\n\n{snippet}"}],
    )

    result: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_recipe":
            result = block.input
            break

    if not result:
        logger.warning("recipe %d: classifier returned no tool call", recipe.id)
        return recipe

    recipe.difficulty = result.get("difficulty")
    recipe.cuisine = result.get("cuisine")
    recipe.meal_type = result.get("meal_type")

    steps = result.get("quick_steps") or []
    recipe.quick_steps = json.dumps(steps[:3]) if steps else None

    try:
        db.commit()
        db.refresh(recipe)
    except Exception:
        db.rollback()
        raise

    logger.debug(
        "recipe %d classified: difficulty=%s cuisine=%s meal_type=%s",
        recipe.id, recipe.difficulty, recipe.cuisine, recipe.meal_type,
    )
    return recipe


# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------

def classify_unclassified(
    db: Session,
    *,
    client: Optional[anthropic.Anthropic] = None,
    limit: int = 200,
) -> int:
    """Classify all recipes missing at least one label. Returns count classified."""
    from sqlalchemy import or_

    recipes = (
        db.query(RawRecipe)
        .filter(
            or_(
                RawRecipe.difficulty.is_(None),
                RawRecipe.cuisine.is_(None),
                RawRecipe.meal_type.is_(None),
                RawRecipe.quick_steps.is_(None),
            )
        )
        .limit(limit)
        .all()
    )

    if not recipes:
        return 0

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    count = 0
    for recipe in recipes:
        try:
            classify_recipe(db, recipe, client=client)
            count += 1
        except Exception as exc:
            logger.warning("recipe %d: classification failed — %s", recipe.id, exc)

    logger.info("Classified %d recipe(s)", count)
    return count

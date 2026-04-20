"""Recipe classifier.

Uses Claude tool-use to label each RawRecipe with:
  - difficulty   : "easy" | "medium" | "complex"
  - cuisine      : e.g. "Asian", "Italian", "American", "Mexican", ...
  - meal_type    : "breakfast" | "lunch" | "dinner" | "any"
  - quick_steps  : JSON list of 3 short cooking-method bullet strings
  - prep_time    : total minutes (int)
  - dietary_tags : JSON list from fixed set (gluten-free, dairy-free, vegetarian, vegan, nut-free)
  - spice_level  : "mild" | "medium" | "hot"
  - servings     : number of servings (int)

Classification is skipped for recipes that already have all eight fields set.
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
        "and summarise the cooking method in 3 short steps. "
        "Also extract prep time, dietary tags, spice level, and servings."
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
            "prep_time": {
                "type": "integer",
                "description": (
                    "Total time in minutes from start to serving, including "
                    "any marinating or resting time. Estimate if not stated."
                ),
            },
            "dietary_tags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["gluten-free", "dairy-free", "vegetarian", "vegan", "nut-free"],
                },
                "description": (
                    "Dietary labels that genuinely apply to this recipe. "
                    "Only include tags you are confident about. May be empty."
                ),
            },
            "spice_level": {
                "type": "string",
                "enum": ["mild", "medium", "hot"],
                "description": (
                    "mild = no heat; medium = some chilli/pepper warmth; "
                    "hot = significant heat from chilli or spices."
                ),
            },
            "servings": {
                "type": "integer",
                "description": (
                    "Number of people this recipe serves as written. "
                    "Estimate 2 if not specified."
                ),
            },
        },
        "required": [
            "difficulty", "cuisine", "meal_type", "quick_steps",
            "prep_time", "dietary_tags", "spice_level", "servings",
        ],
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
    if (
        recipe.difficulty and recipe.cuisine and recipe.meal_type and recipe.quick_steps
        and recipe.prep_time is not None and recipe.dietary_tags is not None
        and recipe.spice_level and recipe.servings is not None
    ):
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

    recipe.prep_time = result.get("prep_time")
    recipe.dietary_tags = json.dumps(result.get("dietary_tags") or [])
    recipe.spice_level = result.get("spice_level")
    recipe.servings = result.get("servings")

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
                RawRecipe.prep_time.is_(None),
                RawRecipe.dietary_tags.is_(None),
                RawRecipe.spice_level.is_(None),
                RawRecipe.servings.is_(None),
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


# ---------------------------------------------------------------------------
# Component classification  (Base / Flavor / Protein)
# ---------------------------------------------------------------------------

_COMPONENTS_TOOL: anthropic.types.ToolParam = {
    "name": "identify_components",
    "description": (
        "Identify the key meal components of a recipe: the base (grain/starch), "
        "the flavor (sauce or glaze — give it a descriptive name), and the protein. "
        "Only include roles that clearly apply."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {
                            "type": "string",
                            "enum": ["base", "flavor", "protein", "other"],
                            "description": (
                                "base = grain/starch/bulk veg cooked in batch; "
                                "flavor = sauce, glaze, or marinade (name it descriptively); "
                                "protein = main protein source; "
                                "other = anything else worth highlighting"
                            ),
                        },
                        "label": {
                            "type": "string",
                            "description": (
                                "Specific display name. For flavor, infer the sauce name from "
                                "the ingredient cluster (e.g. 'Honey Garlic Glaze', "
                                "'Teriyaki Sauce', 'Creamy Tomato Base'). "
                                "For base and protein, use the ingredient name."
                            ),
                        },
                    },
                    "required": ["role", "label"],
                },
                "minItems": 1,
                "maxItems": 4,
            },
        },
        "required": ["components"],
    },
}


def classify_components(
    db: Session,
    recipe: RawRecipe,
    *,
    client: Optional[anthropic.Anthropic] = None,
    force: bool = False,
) -> int:
    """Identify base/flavor/protein components for a recipe. Returns count of components saved."""
    from app.db.models import Ingredient, RecipeComponent

    if not force:
        existing = db.query(RecipeComponent).filter(RecipeComponent.recipe_id == recipe.id).count()
        if existing > 0:
            return 0

    ings = db.query(Ingredient).filter(Ingredient.recipe_id == recipe.id).all()
    if not ings:
        return 0

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    title = recipe.raw_content.strip().splitlines()[0][:80] if recipe.raw_content.strip() else "Unknown"
    ing_list = "; ".join(
        " ".join(filter(None, [i.quantity, i.unit, i.ingredient_name])).strip()
        for i in ings
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            tools=[_COMPONENTS_TOOL],
            tool_choice={"type": "tool", "name": "identify_components"},
            messages=[{
                "role": "user",
                "content": (
                    f"Recipe: {title}\n"
                    f"Ingredients: {ing_list}\n\n"
                    "Identify up to 4 components (base, flavor, protein, other). "
                    "For the flavor role, infer a descriptive sauce/glaze name."
                ),
            }],
        )
    except Exception as exc:
        logger.warning("classify_components: recipe %d API call failed — %s", recipe.id, exc)
        return 0

    components: list[dict] = []
    for block in resp.content:
        if block.type == "tool_use" and block.name == "identify_components":
            components = block.input.get("components", [])
            break

    if not components:
        return 0

    # Remove any existing components before writing (handles force=True)
    db.query(RecipeComponent).filter(RecipeComponent.recipe_id == recipe.id).delete()

    for order, comp in enumerate(components):
        db.add(RecipeComponent(
            recipe_id=recipe.id,
            role=comp["role"],
            label=comp["label"],
            display_order=order,
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.debug("recipe %d: %d component(s) saved", recipe.id, len(components))
    return len(components)


def classify_unclassified_components(
    db: Session,
    *,
    client: Optional[anthropic.Anthropic] = None,
    limit: int = 100,
) -> int:
    """Classify components for recipes that have ingredients but no components yet."""
    from sqlalchemy import exists
    from app.db.models import Ingredient, RecipeComponent

    subq = exists().where(RecipeComponent.recipe_id == RawRecipe.id)
    has_ings = exists().where(Ingredient.recipe_id == RawRecipe.id)

    recipes = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.difficulty.isnot(None),
            has_ings,
            ~subq,
        )
        .limit(limit)
        .all()
    )

    if not recipes:
        return 0

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    total = 0
    for recipe in recipes:
        try:
            total += classify_components(db, recipe, client=client)
        except Exception as exc:
            logger.warning("classify_components batch: recipe %d failed — %s", recipe.id, exc)

    logger.info("Component classification: %d component(s) saved across %d recipe(s)", total, len(recipes))
    return total

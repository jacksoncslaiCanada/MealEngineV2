"""Phase 2 ingredient extractor.

Calls Claude to extract structured ingredient records from raw recipe text,
persists them to the `ingredients` table, and skips recipes that have already
been processed.

Structured output is obtained via tool-use: Claude is forced to call the
``record_ingredients`` tool, whose JSON-schema input is our output format.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ingredient, RawRecipe
from app.normaliser import normalise_ingredient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definition for structured extraction
# ---------------------------------------------------------------------------

_EXTRACT_TOOL: anthropic.types.ToolParam = {
    "name": "record_ingredients",
    "description": (
        "Record the structured ingredient list extracted from the recipe text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ingredients": {
                "type": "array",
                "description": "All ingredients found in the recipe.",
                "items": {
                    "type": "object",
                    "properties": {
                        "ingredient_name": {
                            "type": "string",
                            "description": (
                                "Core ingredient name, singular, lower-case, "
                                "without preparation notes (e.g. 'chicken breast', 'olive oil')"
                            ),
                        },
                        "quantity": {
                            "type": ["string", "null"],
                            "description": "Numeric amount as string, or null (e.g. '2', '1/2', '3.5')",
                        },
                        "unit": {
                            "type": ["string", "null"],
                            "description": "Unit of measure, or null (e.g. 'cup', 'tbsp', 'g', 'oz')",
                        },
                    },
                    "required": ["ingredient_name", "quantity", "unit"],
                },
            }
        },
        "required": ["ingredients"],
    },
}

_SYSTEM_PROMPT = """\
You are a culinary data extraction assistant. Given the raw text of a recipe,
extract every ingredient mentioned and call the record_ingredients tool with
the structured list.

Rules:
- ingredient_name: the core ingredient, singular, lower-case (e.g. "chicken breast", "olive oil")
- quantity: numeric amount as a string, or null if not stated (e.g. "2", "1/2", "3.5")
- unit: unit of measure as a string, or null if not stated (e.g. "cup", "tbsp", "g", "oz")
- Do NOT include preparation notes in ingredient_name (e.g. "diced", "chopped")
- Include ALL ingredients, including optional ones
"""

_USER_TEMPLATE = "Extract the ingredients from the following recipe:\n\n{raw_content}"


# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------

def extract_ingredients(
    db: Session,
    recipe: RawRecipe,
    *,
    client: Optional[anthropic.Anthropic] = None,
) -> list[Ingredient]:
    """Extract structured ingredients from a single recipe using Claude.

    Skips (returns empty list) if the recipe already has ingredient rows.
    Returns the newly created and committed ``Ingredient`` ORM objects.
    """
    # Deduplication: skip if already processed
    existing = (
        db.query(Ingredient).filter(Ingredient.recipe_id == recipe.id).first()
    )
    if existing is not None:
        logger.debug("recipe %d already processed — skipping", recipe.id)
        return []

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    logger.info("Extracting ingredients for recipe %d (source=%s)", recipe.id, recipe.source)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_ingredients"},
        messages=[
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(raw_content=recipe.raw_content),
            }
        ],
    )

    # Extract the tool_use block — tool_choice forces exactly one
    tool_input: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "record_ingredients":
            tool_input = block.input
            break

    items: list[dict] = tool_input.get("ingredients", [])
    extracted_at = datetime.now(timezone.utc)
    rows: list[Ingredient] = []

    for item in items:
        raw_name = item["ingredient_name"]
        row = Ingredient(
            ingredient_name=raw_name,
            canonical_name=normalise_ingredient(raw_name),
            quantity=item.get("quantity"),
            unit=item.get("unit"),
            recipe_id=recipe.id,
            source_id=recipe.source_fk,
            extracted_at=extracted_at,
        )
        db.add(row)
        rows.append(row)

    try:
        db.commit()
        for row in rows:
            db.refresh(row)
    except Exception:
        db.rollback()
        raise

    logger.info("recipe %d: extracted %d ingredient(s)", recipe.id, len(rows))
    return rows


# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------

def extract_all_unprocessed(
    db: Session,
    *,
    client: Optional[anthropic.Anthropic] = None,
    limit: Optional[int] = None,
) -> list[Ingredient]:
    """Extract ingredients for every recipe not yet in the ingredients table.

    Returns a flat list of all newly created ``Ingredient`` rows.
    """
    # Find recipe IDs that already have at least one ingredient row
    processed_ids = {
        row[0] for row in db.query(Ingredient.recipe_id).distinct().all()
    }

    query = db.query(RawRecipe)
    if processed_ids:
        query = query.filter(RawRecipe.id.notin_(processed_ids))
    # Skip YouTube recipes with no transcript — title+description alone
    # yields 0 ingredients and the recipe would be retried every run.
    query = query.filter(
        ~((RawRecipe.source == "youtube") & (RawRecipe.has_transcript == False))
    )
    if limit is not None:
        query = query.limit(limit)

    recipes = query.all()
    logger.info("Found %d unprocessed recipe(s)", len(recipes))

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    all_rows: list[Ingredient] = []
    for recipe in recipes:
        try:
            rows = extract_ingredients(db, recipe, client=client)
            all_rows.extend(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "recipe %d: extraction failed, skipping — %s", recipe.id, exc
            )

    return all_rows

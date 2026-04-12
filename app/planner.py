"""Meal plan generator.

Selects 7 breakfast + 7 dinner recipes for a given variant, derives
lunch as "Leftovers from [dinner]" or an easy recipe, aggregates a
shopping list, and returns structured plan + shopping dicts.

Variants
--------
weeknight_easy    – all easy; quick weeknight dinners
family_variety    – mixed difficulty, varied cuisines
asian_kitchen     – Asian cuisine prioritised
weekend_cook      – easy on weekdays, medium/complex on Fri–Sun
"""
from __future__ import annotations

import json
import logging
import random
from collections import Counter
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ingredient, MealPlan, RawRecipe

# Ingredients everyone keeps in their pantry — excluded from shopping lists.
_PANTRY_STAPLES: frozenset[str] = frozenset({
    # Salt & pepper
    "salt", "sea salt", "kosher salt", "table salt",
    "pepper", "black pepper", "white pepper", "ground pepper", "ground black pepper",
    # Oils
    "oil", "olive oil", "extra virgin olive oil", "vegetable oil", "canola oil",
    "cooking oil", "neutral oil", "sesame oil",
    # Water & basic liquids
    "water", "ice", "ice water",
    # Sugars
    "sugar", "white sugar", "granulated sugar", "caster sugar",
    # Flour & leavening
    "flour", "all-purpose flour", "plain flour",
    "baking powder", "baking soda", "bicarbonate of soda",
    # Basic aromatics (nearly universal pantry items)
    "garlic", "garlic clove", "garlic powder", "garlic salt",
    "onion powder",
    # Vinegars & condiments
    "vinegar", "white vinegar",
    # Spice pantry basics
    "paprika", "cumin", "dried oregano", "bay leaf", "bay leaves",
    "dried thyme", "chili flakes", "red pepper flakes",
    # Vanilla
    "vanilla", "vanilla extract",
})

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

VARIANTS = {
    "weeknight_easy": "Weeknight Easy",
    "family_variety": "Family Variety",
    "asian_kitchen":  "Asian Kitchen",
    "weekend_cook":   "Weekend Cook",
    "little_ones":    "Little Ones",
    "teen_table":     "Teen Table",
}

# How many weekend days (Fri + Sat + Sun = indices 4,5,6)
_WEEKEND_INDICES = {4, 5, 6}


# ---------------------------------------------------------------------------
# Title helpers
# ---------------------------------------------------------------------------

def _extract_title(raw_content: str) -> str:
    first = raw_content.strip().splitlines()[0] if raw_content.strip() else ""
    for prefix in ("Title: ", "Meal: ", "# ", "## "):
        if first.startswith(prefix):
            return first[len(prefix):].strip()
    return first[:60] or "Untitled"


# ---------------------------------------------------------------------------
# Recipe selection
# ---------------------------------------------------------------------------

def _pick_recipes(
    pool: list[RawRecipe],
    n: int,
    seed: Optional[int] = None,
) -> list[RawRecipe]:
    """Return up to n unique recipes from pool."""
    rng = random.Random(seed)
    available = list(pool)
    rng.shuffle(available)
    return available[:n]


def _pool_for_variant(
    db: Session,
    variant: str,
    meal_type: str,        # "breakfast" or "dinner"
) -> list[RawRecipe]:
    """Return classified recipes appropriate for this variant + meal slot."""
    from sqlalchemy import or_

    # prep_time filter: ≤ 30 min OR NULL (unknown — don't exclude unclassified)
    _quick = or_(RawRecipe.prep_time <= 30, RawRecipe.prep_time.is_(None))

    q = db.query(RawRecipe).filter(
        RawRecipe.difficulty.isnot(None),
        or_(RawRecipe.meal_type == meal_type, RawRecipe.meal_type == "any"),
    )

    if variant == "weeknight_easy":
        q = q.filter(RawRecipe.difficulty == "easy")

    elif variant == "asian_kitchen":
        q = q.filter(RawRecipe.cuisine == "Asian")

    elif variant == "little_ones":
        # Easy only, mild spice, max 30 min — safest recipes for young children
        q = q.filter(
            RawRecipe.difficulty == "easy",
            or_(RawRecipe.spice_level == "mild", RawRecipe.spice_level.is_(None)),
            _quick,
        )

    elif variant == "teen_table":
        # Easy or medium, mild or medium spice, max 30 min
        q = q.filter(
            RawRecipe.difficulty.in_(["easy", "medium"]),
            or_(
                RawRecipe.spice_level.in_(["mild", "medium"]),
                RawRecipe.spice_level.is_(None),
            ),
            _quick,
        )

    # family_variety and weekend_cook: no extra filter — use full classified pool
    return q.all()


# ---------------------------------------------------------------------------
# Shopping list aggregation
# ---------------------------------------------------------------------------

_SHOPPING_CAP = 25   # maximum items on the final shopping list


def _aggregate_shopping(db: Session, recipe_ids: list[int]) -> list[dict]:
    """Group ingredients by canonical_name, strip pantry staples, cap at 25."""
    if not recipe_ids:
        return []

    rows = (
        db.query(Ingredient)
        .filter(Ingredient.recipe_id.in_(recipe_ids))
        .all()
    )

    # Group by canonical name, track how many recipes need each ingredient
    grouped: dict[str, dict] = {}
    recipe_count: Counter = Counter()

    for ing in rows:
        key = (ing.canonical_name or ing.ingredient_name or "").strip().lower()
        if not key:
            continue
        # Skip pantry staples
        if key in _PANTRY_STAPLES:
            continue

        recipe_count[key] += 1
        if key not in grouped:
            grouped[key] = {"ingredient": key, "entries": []}
        entry: dict = {}
        if ing.quantity:
            entry["qty"] = ing.quantity
        if ing.unit:
            entry["unit"] = ing.unit
        grouped[key]["entries"].append(entry)

    # Sort by frequency (most-needed ingredients first), then alphabetically
    sorted_keys = sorted(grouped.keys(), key=lambda k: (-recipe_count[k], k))

    # Cap at shopping limit
    sorted_keys = sorted_keys[:_SHOPPING_CAP]

    # Re-sort final list alphabetically for easy reading in-store
    sorted_keys.sort()

    shopping: list[dict] = []
    for key in sorted_keys:
        item = grouped[key]
        parts = []
        for e in item["entries"]:
            if e.get("qty") and e.get("unit"):
                parts.append(f"{e['qty']} {e['unit']}")
            elif e.get("qty"):
                parts.append(e["qty"])
        shopping.append({
            "ingredient": key,
            "amounts": ", ".join(parts),
        })

    return shopping


# ---------------------------------------------------------------------------
# Main plan builder
# ---------------------------------------------------------------------------

def generate_plan(
    db: Session,
    variant: str,
    week_label: Optional[str] = None,
    seed: Optional[int] = None,
) -> MealPlan:
    """Generate, persist, and return a MealPlan for the given variant/week."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant '{variant}'. Choose from: {list(VARIANTS)}")

    if week_label is None:
        # ISO week of current date
        today = date.today()
        year, week, _ = today.isocalendar()
        week_label = f"{year}-W{week:02d}"

    # Use a deterministic seed from variant + week so same week always picks
    # the same plan; caller can override for testing.
    if seed is None:
        seed = hash(f"{variant}-{week_label}") & 0xFFFFFFFF

    # Fetch breakfast + dinner pools
    breakfast_pool = _pool_for_variant(db, variant, "breakfast")
    dinner_pool = _pool_for_variant(db, variant, "dinner")

    # Fallback 1: relax variant constraints, keep meal_type filter
    if len(breakfast_pool) < 7:
        from sqlalchemy import or_
        breakfast_pool = db.query(RawRecipe).filter(
            RawRecipe.difficulty.isnot(None),
            or_(RawRecipe.meal_type == "breakfast", RawRecipe.meal_type == "any"),
        ).all()

    if len(dinner_pool) < 7:
        from sqlalchemy import or_
        dinner_pool = db.query(RawRecipe).filter(
            RawRecipe.difficulty.isnot(None),
            or_(RawRecipe.meal_type == "dinner", RawRecipe.meal_type == "any"),
        ).all()

    # Fallback 2: no classification required — use all available recipes
    all_recipes = None
    if len(breakfast_pool) < 7 or len(dinner_pool) < 7:
        all_recipes = db.query(RawRecipe).all()
    if len(breakfast_pool) < 7:
        breakfast_pool = all_recipes or db.query(RawRecipe).all()
    if len(dinner_pool) < 7:
        dinner_pool = all_recipes or db.query(RawRecipe).all()

    breakfasts = _pick_recipes(breakfast_pool, 7, seed=seed)
    dinners = _pick_recipes(dinner_pool, 7, seed=seed + 1)

    # For weekend_cook: swap Fri/Sat/Sun dinners for medium/complex if possible
    if variant == "weekend_cook":
        complex_pool = [r for r in dinner_pool if r.difficulty in ("medium", "complex")]
        complex_picks = _pick_recipes(complex_pool, 3, seed=seed + 2)
        for slot, day_idx in enumerate(_WEEKEND_INDICES):
            if slot < len(complex_picks) and day_idx < len(dinners):
                dinners[day_idx] = complex_picks[slot]

    # Classify any selected dinner/breakfast recipes that are missing quick_steps.
    # These are the exact recipes going into the plan, so we do it synchronously now.
    from app.classifier import classify_recipe
    import anthropic as _anthropic
    _client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    for recipe in set(dinners + breakfasts):
        if recipe and not recipe.quick_steps:
            try:
                classify_recipe(db, recipe, client=_client)
            except Exception as exc:
                logger.warning("planner: on-demand classify failed for recipe %d — %s", recipe.id, exc)

    # Build day-by-day schedule
    days: list[dict] = []
    all_recipe_ids: list[int] = []

    for i, day_name in enumerate(DAYS):
        bf = breakfasts[i] if i < len(breakfasts) else None
        dn = dinners[i] if i < len(dinners) else None

        day_entry: dict = {"day": day_name}

        if bf:
            day_entry["breakfast"] = {
                "recipe_id": bf.id,
                "title": _extract_title(bf.raw_content),
                "difficulty": bf.difficulty or "easy",
                "cuisine": bf.cuisine or "",
                "url": bf.url,
                "quick_steps": json.loads(bf.quick_steps) if bf.quick_steps else [],
                "prep_time": bf.prep_time,
                "dietary_tags": json.loads(bf.dietary_tags) if bf.dietary_tags else [],
                "spice_level": bf.spice_level or "mild",
                "servings": bf.servings,
            }
            all_recipe_ids.append(bf.id)
        else:
            day_entry["breakfast"] = {"title": "Your choice", "difficulty": "easy"}

        # Lunch = leftovers from previous night's dinner
        prev_dinner = dinners[i - 1] if i > 0 and (i - 1) < len(dinners) else None
        if prev_dinner:
            day_entry["lunch"] = {
                "title": f"Leftovers: {_extract_title(prev_dinner.raw_content)}",
                "note": "Pack the night before",
            }
        else:
            day_entry["lunch"] = {"title": "Packed lunch / your choice", "note": ""}

        if dn:
            day_entry["dinner"] = {
                "recipe_id": dn.id,
                "title": _extract_title(dn.raw_content),
                "difficulty": dn.difficulty or "easy",
                "cuisine": dn.cuisine or "",
                "url": dn.url,
                "quick_steps": json.loads(dn.quick_steps) if dn.quick_steps else [],
                "prep_time": dn.prep_time,
                "dietary_tags": json.loads(dn.dietary_tags) if dn.dietary_tags else [],
                "spice_level": dn.spice_level or "mild",
                "servings": dn.servings,
            }
            all_recipe_ids.append(dn.id)
        else:
            day_entry["dinner"] = {"title": "Your choice", "difficulty": "easy", "cuisine": ""}

        days.append(day_entry)

    shopping = _aggregate_shopping(db, list(set(all_recipe_ids)))

    plan = MealPlan(
        variant=variant,
        week_label=week_label,
        plan_json=json.dumps(days),
        shopping_json=json.dumps(shopping),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

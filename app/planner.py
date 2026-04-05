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
import random
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import Ingredient, MealPlan, RawRecipe

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

VARIANTS = {
    "weeknight_easy": "Weeknight Easy",
    "family_variety": "Family Variety",
    "asian_kitchen":  "Asian Kitchen",
    "weekend_cook":   "Weekend Cook",
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

    q = db.query(RawRecipe).filter(
        RawRecipe.difficulty.isnot(None),
        or_(RawRecipe.meal_type == meal_type, RawRecipe.meal_type == "any"),
    )

    if variant == "weeknight_easy":
        q = q.filter(RawRecipe.difficulty == "easy")

    elif variant == "asian_kitchen":
        q = q.filter(RawRecipe.cuisine == "Asian")

    # family_variety and weekend_cook: no extra filter — use full classified pool
    return q.all()


# ---------------------------------------------------------------------------
# Shopping list aggregation
# ---------------------------------------------------------------------------

def _aggregate_shopping(db: Session, recipe_ids: list[int]) -> list[dict]:
    """Group ingredients by canonical_name across all recipes."""
    if not recipe_ids:
        return []

    rows = (
        db.query(Ingredient)
        .filter(Ingredient.recipe_id.in_(recipe_ids))
        .all()
    )

    grouped: dict[str, dict] = {}
    for ing in rows:
        key = ing.canonical_name or ing.ingredient_name
        if key not in grouped:
            grouped[key] = {"ingredient": key, "entries": []}
        entry: dict = {}
        if ing.quantity:
            entry["qty"] = ing.quantity
        if ing.unit:
            entry["unit"] = ing.unit
        grouped[key]["entries"].append(entry)

    # Build display list sorted alphabetically
    shopping: list[dict] = []
    for key in sorted(grouped.keys()):
        item = grouped[key]
        # Summarise quantities as a simple string list
        parts = []
        for e in item["entries"]:
            if e.get("qty") and e.get("unit"):
                parts.append(f"{e['qty']} {e['unit']}")
            elif e.get("qty"):
                parts.append(e["qty"])
        shopping.append({
            "ingredient": key,
            "amounts": ", ".join(parts) if parts else "as needed",
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
                "url": bf.url,
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

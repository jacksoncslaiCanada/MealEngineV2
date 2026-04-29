"""Generate 9-page Weekly Anchor PDFs.

Pages: cover + 5 recipe cards + macro guide + shopping list + pantry sides.
Reuses rendering infrastructure from theme_pack_generator.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.themes import ThemePack

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def generate_weekly_anchor_pdf(theme: "ThemePack", db: "Session") -> bytes:
    """Return PDF bytes for a 9-page Weekly Anchor.

    Raises ValueError if fewer than 5 suitable recipes are found.
    """
    from jinja2 import Environment, FileSystemLoader
    from app.theme_selector import select_recipes_for_theme
    from app.db.models import RawRecipe, Ingredient, RecipeComponent
    from app.card_renderer import _macro_pct, _extract_title, ingredient_to_dict
    from app.pdf_renderer import _render_with_playwright
    from app.theme_pack_generator import (
        _render_single_page, _render_full_bleed, _merge_pdfs,
        _build_shopping_list, DIFFICULTY_COLORS, DIETARY_ABBR,
    )

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

    # ── 1. Select 5 recipes via Claude ───────────────────────────────────────
    ids = select_recipes_for_theme(theme, db, limit=5)

    # ── 2. Load recipe rows ──────────────────────────────────────────────────
    recipes_db = db.query(RawRecipe).filter(RawRecipe.id.in_(ids)).all()
    by_id = {r.id: r for r in recipes_db}

    # ── 3. Cover thumbnail data ──────────────────────────────────────────────
    cover_recipes = [
        {
            "title":     by_id[i].card_title or "",
            "cuisine":   by_id[i].cuisine or "",
            "image_url": by_id[i].card_image_url,
            "prep_time": by_id[i].prep_time,
        }
        for i in ids if i in by_id
    ]

    # ── 4. Full recipe dicts + nutrition data ────────────────────────────────
    card_recipes = []
    all_shopping_ings: list[dict] = []
    nutrition_rows: list[dict] = []
    recipe_titles: list[str] = []
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    macro_count = 0
    total_servings = 0

    for idx, recipe_id in enumerate(ids):
        if recipe_id not in by_id:
            continue
        r = by_id[recipe_id]
        day = _DAYS[idx] if idx < len(_DAYS) else f"Day {idx + 1}"

        ings = db.query(Ingredient).filter(Ingredient.recipe_id == r.id).all()
        comps = (
            db.query(RecipeComponent)
            .filter(RecipeComponent.recipe_id == r.id)
            .order_by(RecipeComponent.display_order)
            .all()
        )

        dietary_tags = json.loads(r.dietary_tags) if r.dietary_tags else []
        card_steps   = json.loads(r.card_steps)   if r.card_steps   else []
        quick_steps  = json.loads(r.quick_steps)  if r.quick_steps  else []

        title = (
            r.card_title
            or _extract_title(r.raw_content or "")
            or (r.card_summary or "").split(".")[0].strip()
            or r.cuisine
            or "Recipe"
        )
        recipe_titles.append(title)
        total_servings += r.servings or 4

        card_recipes.append({
            "title":           title,
            "cuisine":         r.cuisine or "",
            "difficulty":      r.difficulty or "",
            "prep_time":       r.prep_time,
            "servings":        r.servings or 4,
            "dietary_tags":    dietary_tags,
            "url":             r.url,
            "image_url":       r.card_image_url,
            "card_steps":      card_steps,
            "quick_steps":     quick_steps,
            "card_tip":        r.card_tip or "",
            "card_summary":    r.card_summary or "",
            "side_suggestion": r.side_suggestion or "",
            "ingredients":     [ingredient_to_dict(ing) for ing in ings],
            "components":      [{"role": c.role, "label": c.label} for c in comps],
            "macros":          {},
            "macro_pct":       _macro_pct({}),
        })

        nutrition_rows.append({
            "day":       day,
            "title":     title,
            "calories":  r.calories,
            "protein_g": r.protein_g,
            "carbs_g":   r.carbs_g,
            "fat_g":     r.fat_g,
        })

        if r.calories is not None:
            totals["calories"]  += r.calories
            totals["protein_g"] += r.protein_g or 0
            totals["carbs_g"]   += r.carbs_g   or 0
            totals["fat_g"]     += r.fat_g      or 0
            macro_count += 1

        for ing in ings:
            all_shopping_ings.append({
                "name":           ing.ingredient_name,
                "canonical_name": ing.canonical_name,
                "qty":            (ing.quantity or "").strip(),
                "unit":           (ing.unit or "").strip(),
                "category":       ing.category,
            })

    # ── 5. Macro averages ────────────────────────────────────────────────────
    if macro_count:
        averages = {
            "calories":  totals["calories"]  // macro_count,
            "protein_g": totals["protein_g"] // macro_count,
            "carbs_g":   totals["carbs_g"]   // macro_count,
            "fat_g":     totals["fat_g"]      // macro_count,
        }
        display_totals = totals
    else:
        averages = {"calories": None, "protein_g": None, "carbs_g": None, "fat_g": None}
        display_totals = {"calories": None, "protein_g": None, "carbs_g": None, "fat_g": None}

    avg_servings = round(total_servings / len(ids)) if ids else 4

    # ── 6. Render cover ──────────────────────────────────────────────────────
    cover_html = env.get_template("weekly_anchor_cover.html").render(
        theme=theme,
        recipes=cover_recipes,
        days=_DAYS,
    )
    cover_pdf = _render_single_page(cover_html)
    logger.info("weekly_anchor: cover rendered (%d bytes)", len(cover_pdf))

    # ── 7. Render 5 recipe cards ─────────────────────────────────────────────
    cards_html = env.get_template("recipe_card_flow.html").render(
        recipes=card_recipes,
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )
    cards_pdf = _render_with_playwright(cards_html, week_label=theme.name)
    logger.info("weekly_anchor: recipe cards rendered (%d bytes)", len(cards_pdf))

    # ── 8. Render macro guide ────────────────────────────────────────────────
    macro_pdf: bytes | None = None
    try:
        macro_html = env.get_template("macro_guide.html").render(
            theme=theme,
            nutrition_rows=nutrition_rows,
            totals=display_totals,
            averages=averages,
            total_recipes=len(nutrition_rows),
            avg_servings=avg_servings,
        )
        macro_pdf = _render_full_bleed(macro_html)
        logger.info("weekly_anchor: macro guide rendered (%d bytes)", len(macro_pdf))
    except Exception as exc:
        logger.error("weekly_anchor: macro guide failed — %s", exc, exc_info=True)

    # ── 9. Render shopping list ──────────────────────────────────────────────
    shopping_pdf: bytes | None = None
    try:
        aisles = _build_shopping_list(all_shopping_ings)
        shopping_html = env.get_template("shopping_list.html").render(
            theme=theme,
            aisles=aisles,
            recipe_titles=recipe_titles,
            total_recipes=len(recipe_titles),
            total_servings=total_servings,
        )
        shopping_pdf = _render_full_bleed(shopping_html)
        logger.info("weekly_anchor: shopping list rendered (%d bytes)", len(shopping_pdf))
    except Exception as exc:
        logger.error("weekly_anchor: shopping list failed — %s", exc, exc_info=True)

    # ── 10. Render pantry sides ──────────────────────────────────────────────
    pantry_pdf: bytes | None = None
    try:
        pantry_html = env.get_template("pantry_sides.html").render(theme=theme)
        pantry_pdf = _render_full_bleed(pantry_html)
        logger.info("weekly_anchor: pantry sides rendered (%d bytes)", len(pantry_pdf))
    except Exception as exc:
        logger.error("weekly_anchor: pantry sides failed — %s", exc, exc_info=True)

    # ── 11. Merge all pages ──────────────────────────────────────────────────
    pdf_parts = [cover_pdf, cards_pdf]
    for optional in [macro_pdf, shopping_pdf, pantry_pdf]:
        if optional:
            pdf_parts.append(optional)

    merged = _merge_pdfs(pdf_parts)
    page_count = 1 + len(card_recipes) + sum(
        1 for p in [macro_pdf, shopping_pdf, pantry_pdf] if p
    )
    logger.info(
        "weekly_anchor: merged PDF for '%s' — %d pages, %d bytes",
        theme.slug, page_count, len(merged),
    )
    return merged

"""Generate 4-page theme pack PDFs: cover page + 3 recipe cards.

Combines theme_cover.html and recipe_card_flow.html into a single
Playwright render. A small CSS override block resolves the two
class-name conflicts (.card-title, .section-header) between templates.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.themes import ThemePack

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"

DIFFICULTY_COLORS = {
    "easy":    "#687f6a",
    "medium":  "#c9943a",
    "complex": "#b5614a",
}

DIETARY_ABBR = {
    "gluten-free": "GF",
    "dairy-free":  "DF",
    "vegetarian":  "V",
    "vegan":       "VG",
    "nut-free":    "NF",
}

# Restores cover-specific styles that the recipe-card stylesheet would override.
# Specificity: .recipe-card .card-title (0-2-0) beats .card-title (0-1-0).
_CSS_OVERRIDES = """
.recipe-card .card-title {
  font-size: 7.5pt;
  color: #2c2c2c;
  line-height: 1.3;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  font-weight: 700;
  white-space: normal;
  text-transform: none;
  letter-spacing: normal;
  width: auto;
  text-overflow: clip;
  margin-bottom: 0;
}
.section-rule .section-header {
  font-size: 7pt;
  letter-spacing: 0.22em;
  color: #2c2c2c;
  font-family: 'Playfair Display', serif;
  font-weight: 700;
}
"""


def _extract_styles(html: str) -> str:
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL))


def _extract_body(html: str) -> str:
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    return m.group(1).strip() if m else html


def _combine_html(cover_html: str, cards_html: str) -> str:
    cover_css = _extract_styles(cover_html)
    cards_css = _extract_styles(cards_html)
    cover_body = _extract_body(cover_html)
    cards_body = _extract_body(cards_html)

    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n"
        "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n"
        "<link href=\"https://fonts.googleapis.com/css2?family=Playfair+Display"
        ":wght@700;900&family=Lora:ital,wght@0,400;0,600;1,400&display=swap\" rel=\"stylesheet\">\n"
        "<style>\n"
        + cover_css + "\n"
        + cards_css + "\n"
        + _CSS_OVERRIDES
        + ".page-break { page-break-before: always; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        + cover_body + "\n"
        "<div class=\"page-break\"></div>\n"
        + cards_body + "\n"
        "</body>\n"
        "</html>"
    )


def generate_theme_pack_pdf(theme: "ThemePack", db: "Session") -> bytes:
    """Return PDF bytes for a 4-page theme pack (cover + 3 recipe cards).

    Raises ValueError if fewer than 3 suitable recipes are found.
    """
    from jinja2 import Environment, FileSystemLoader
    from app.theme_selector import select_recipes_for_theme
    from app.db.models import RawRecipe, Ingredient, RecipeComponent
    from app.card_renderer import _macro_pct, _extract_title
    from app.pdf_renderer import _render_with_playwright

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

    # ── 1. Select 3 recipes via Claude ────────────────────────────────────────
    ids = select_recipes_for_theme(theme, db)

    # ── 2. Load recipe rows ───────────────────────────────────────────────────
    recipes_db = db.query(RawRecipe).filter(RawRecipe.id.in_(ids)).all()
    by_id = {r.id: r for r in recipes_db}

    # ── 3. Cover thumbnail cards (compact) ────────────────────────────────────
    cover_recipes = [
        {
            "title":     by_id[i].card_title or "",
            "cuisine":   by_id[i].cuisine or "",
            "image_url": by_id[i].card_image_url,
            "prep_time": by_id[i].prep_time,
        }
        for i in ids if i in by_id
    ]

    # ── 4. Full recipe dicts for recipe card pages ────────────────────────────
    card_recipes = []
    for i in ids:
        if i not in by_id:
            continue
        r = by_id[i]

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

        card_recipes.append({
            "title":        title,
            "cuisine":      r.cuisine or "",
            "difficulty":   r.difficulty or "",
            "prep_time":    r.prep_time,
            "servings":     r.servings or 4,
            "dietary_tags": dietary_tags,
            "url":          r.url,
            "image_url":    r.card_image_url,
            "card_steps":   card_steps,
            "quick_steps":  quick_steps,
            "card_tip":     r.card_tip or "",
            "card_summary": r.card_summary or "",
            "ingredients": [
                {"name": ing.ingredient_name, "qty": ing.quantity or "", "unit": ing.unit or ""}
                for ing in ings
            ],
            "components": [
                {"role": c.role, "label": c.label}
                for c in comps
            ],
            "macros":    {},
            "macro_pct": _macro_pct({}),
        })

    # ── 5. Render templates ───────────────────────────────────────────────────
    cover_html = env.get_template("theme_cover.html").render(
        theme=theme,
        recipes=cover_recipes,
    )
    cards_html = env.get_template("recipe_card_flow.html").render(
        recipes=card_recipes,
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )

    # ── 6. Combine + render ───────────────────────────────────────────────────
    combined_html = _combine_html(cover_html, cards_html)

    logger.info(
        "theme_pack_generator: rendering '%s' — %d recipes",
        theme.slug, len(card_recipes),
    )
    return _render_with_playwright(combined_html, week_label=theme.name)

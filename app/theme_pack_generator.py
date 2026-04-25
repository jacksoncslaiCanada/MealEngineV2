"""Generate 4-page theme pack PDFs: cover page + 3 recipe cards.

Renders the cover and the recipe cards as two completely independent
Playwright PDFs (no shared CSS), then merges them with pypdf.
This eliminates all stylesheet interaction between the two templates.
"""
from __future__ import annotations

import io
import json
import logging
import os
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


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def _render_single_page(html_str: str) -> bytes:
    """Render HTML to a single-page PDF with no header/footer chrome."""
    from playwright.sync_api import sync_playwright

    launch_kwargs: dict = {}
    if ep := os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
        launch_kwargs["executable_path"] = ep

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page()
        page.set_content(html_str, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "14mm", "right": "16mm", "bottom": "16mm", "left": "16mm"},
            display_header_footer=False,
        )
        browser.close()

    return pdf_bytes


def _merge_pdfs(pdfs: list[bytes]) -> bytes:
    """Concatenate a list of PDF byte strings into one PDF."""
    from pdfrw import PdfReader, PdfWriter

    writer = PdfWriter()
    for blob in pdfs:
        reader = PdfReader(io.BytesIO(blob))
        writer.addpages(reader.pages)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_theme_pack_pdf(theme: "ThemePack", db: "Session") -> bytes:
    """Return PDF bytes for a 4-page theme pack (cover + 3 recipe cards).

    Raises ValueError if fewer than 3 suitable recipes are found.
    """
    from jinja2 import Environment, FileSystemLoader
    from app.theme_selector import select_recipes_for_theme
    from app.db.models import RawRecipe, Ingredient, RecipeComponent
    from app.card_renderer import _macro_pct, _extract_title, ingredient_to_dict
    from app.pdf_renderer import _render_with_playwright

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

    # ── 1. Select 3 recipes via Claude ────────────────────────────────────────
    ids = select_recipes_for_theme(theme, db)

    # ── 2. Load recipe rows ───────────────────────────────────────────────────
    recipes_db = db.query(RawRecipe).filter(RawRecipe.id.in_(ids)).all()
    by_id = {r.id: r for r in recipes_db}

    # ── 3. Cover thumbnail data (compact) ─────────────────────────────────────
    cover_recipes = [
        {
            "title":     by_id[i].card_title or "",
            "cuisine":   by_id[i].cuisine or "",
            "image_url": by_id[i].card_image_url,
            "prep_time": by_id[i].prep_time,
        }
        for i in ids if i in by_id
    ]

    # ── 4. Full recipe dicts for card pages ───────────────────────────────────
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
                ingredient_to_dict(ing)
                for ing in ings
            ],
            "components": [
                {"role": c.role, "label": c.label}
                for c in comps
            ],
            "macros":    {},
            "macro_pct": _macro_pct({}),
        })

    # ── 5. Render cover as standalone PDF (no footer chrome) ──────────────────
    cover_html = env.get_template("theme_cover.html").render(
        theme=theme,
        recipes=cover_recipes,
    )
    cover_pdf = _render_single_page(cover_html)
    logger.info("theme_pack_generator: cover page rendered (%d bytes)", len(cover_pdf))

    # ── 6. Render recipe cards as standalone PDF ──────────────────────────────
    cards_html = env.get_template("recipe_card_flow.html").render(
        recipes=card_recipes,
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )
    cards_pdf = _render_with_playwright(cards_html, week_label=theme.name)
    logger.info("theme_pack_generator: recipe cards rendered (%d bytes)", len(cards_pdf))

    # ── 7. Merge cover + cards ────────────────────────────────────────────────
    merged = _merge_pdfs([cover_pdf, cards_pdf])
    logger.info(
        "theme_pack_generator: merged PDF for '%s' — %d pages, %d bytes",
        theme.slug, 4, len(merged),
    )
    return merged

"""Generate 5-page theme pack PDFs: cover page + 3 recipe cards + shopping list.

Renders cover, recipe cards, and shopping list as three independent
Playwright PDFs (no shared CSS), then merges them with pdfrw.
"""
from __future__ import annotations

import io
import json
import logging
import os
from collections import defaultdict
from fractions import Fraction
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
    "gluten-free": "Gluten-Free",
    "dairy-free":  "Dairy-Free",
    "vegetarian":  "Vegetarian",
    "vegan":       "Vegan",
    "nut-free":    "Nut-Free",
}

# Grocery store aisle order for the shopping list page
_AISLE_ORDER: list[tuple[str | None, str]] = [
    ("produce",       "Produce"),
    ("meat & seafood","Meat & Seafood"),
    ("dairy & eggs",  "Dairy & Eggs"),
    ("bakery",        "Bakery"),
    ("pantry",        "Pantry & Dry Goods"),
    ("spices",        "Spices & Seasonings"),
    ("frozen",        "Frozen"),
]


# ---------------------------------------------------------------------------
# Quantity helpers
# ---------------------------------------------------------------------------

def _parse_qty(s: str) -> "Fraction | None":
    """Parse '1/2', '1 1/2', '2', '3.5' → Fraction; None if unparseable."""
    if not s:
        return None
    s = s.strip()
    try:
        parts = s.split()
        if len(parts) == 2:          # mixed number e.g. "1 1/2"
            return Fraction(parts[0]) + Fraction(parts[1])
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def _fmt_qty(f: "Fraction") -> str:
    """Format Fraction as readable string: 7/4 → '1 3/4', 2 → '2'."""
    if f.denominator == 1:
        return str(f.numerator)
    whole = int(f)
    rem = f - whole
    if whole:
        return f"{whole} {rem}"
    return str(f)


# ---------------------------------------------------------------------------
# Shopping list aggregation
# ---------------------------------------------------------------------------

def _build_shopping_list(ingredients: list[dict]) -> list[dict]:
    """Aggregate + deduplicate ingredients and group by grocery store aisle.

    Input dicts need keys: name, canonical_name (optional), qty, unit, category.
    Returns a list of {"aisle": str, "items": [...]} in store-walk order.
    """
    # Group by (canonical_name_lower, unit_lower) — same name+unit → sum qtys
    groups: dict[tuple, dict] = {}

    for ing in ingredients:
        canon = (ing.get("canonical_name") or ing.get("name") or "").strip().lower()
        if not canon:
            continue
        unit     = (ing.get("unit") or "").strip().lower()
        qty_str  = (ing.get("qty") or "").strip()
        category = (ing.get("category") or "").strip().lower() or None

        key = (canon, unit)
        if key not in groups:
            groups[key] = {
                "display_name": ing.get("name") or canon,
                "unit":         ing.get("unit") or "",
                "category":     category,
                "qty_fracs":    [],
                "qty_raw":      [],
                "has_unparseable": False,
            }

        g = groups[key]
        # Adopt a category if we see one and don't already have it
        if category and not g["category"]:
            g["category"] = category

        if qty_str:
            frac = _parse_qty(qty_str)
            if frac is not None:
                g["qty_fracs"].append(frac)
            else:
                g["has_unparseable"] = True
                if qty_str not in g["qty_raw"]:
                    g["qty_raw"].append(qty_str)

    # Build display items, grouped by aisle key
    items_by_aisle: dict[str | None, list[dict]] = defaultdict(list)

    for g in groups.values():
        if g["qty_fracs"]:
            total = sum(g["qty_fracs"], Fraction(0))
            qty_display = _fmt_qty(total)
            if g["has_unparseable"]:
                qty_display += " + " + " + ".join(g["qty_raw"])
        elif g["qty_raw"]:
            qty_display = " + ".join(g["qty_raw"])
        else:
            qty_display = ""  # to taste / unquantified

        items_by_aisle[g["category"]].append({
            "name":        g["display_name"],
            "qty_display": qty_display,
            "unit":        g["unit"],
            "to_taste":    not qty_display,
        })

    # Sort each aisle: measured items first (alphabetical), then to-taste (alphabetical)
    for lst in items_by_aisle.values():
        lst.sort(key=lambda x: (x["to_taste"], x["name"].lower()))

    # Assemble in aisle order
    result = []
    for aisle_key, aisle_label in _AISLE_ORDER:
        if items_by_aisle.get(aisle_key):
            result.append({"aisle": aisle_label, "items": items_by_aisle[aisle_key]})

    # Uncategorized fallback (NULL category) — rendered last as "Other"
    if items_by_aisle.get(None):
        result.append({"aisle": "Other", "items": items_by_aisle[None]})

    return result


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
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
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
    """Return PDF bytes for a 5-page theme pack (cover + 3 recipe cards + shopping list).

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

    # ── 4. Full recipe dicts for card pages + shopping list data ──────────────
    card_recipes = []
    all_shopping_ings: list[dict] = []   # aggregated across all 3 recipes
    recipe_titles: list[str] = []
    total_servings = 0

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
        recipe_titles.append(title)
        total_servings += r.servings or 4

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
            "ingredients": [ingredient_to_dict(ing) for ing in ings],
            "components":  [{"role": c.role, "label": c.label} for c in comps],
            "macros":    {},
            "macro_pct": _macro_pct({}),
        })

        # Collect full ingredient data (with category) for the shopping list
        for ing in ings:
            qty  = (ing.quantity or "").strip()
            unit = (ing.unit or "").strip()
            all_shopping_ings.append({
                "name":           ing.ingredient_name,
                "canonical_name": ing.canonical_name,
                "qty":            qty,
                "unit":           unit,
                "category":       ing.category,
            })

    # ── 5. Render cover as standalone PDF ─────────────────────────────────────
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

    # ── 7. Build and render shopping list page ────────────────────────────────
    aisles = _build_shopping_list(all_shopping_ings)
    shopping_html = env.get_template("shopping_list.html").render(
        theme=theme,
        aisles=aisles,
        recipe_titles=recipe_titles,
        total_recipes=len(recipe_titles),
        total_servings=total_servings,
    )
    shopping_pdf = _render_single_page(shopping_html)
    logger.info("theme_pack_generator: shopping list rendered (%d bytes)", len(shopping_pdf))

    # ── 8. Merge cover + cards + shopping list ────────────────────────────────
    merged = _merge_pdfs([cover_pdf, cards_pdf, shopping_pdf])
    logger.info(
        "theme_pack_generator: merged PDF for '%s' — %d pages, %d bytes",
        theme.slug, 5, len(merged),
    )
    return merged

"""
DB-connected recipe card preview — renders real recipes from your database.

Usage:
    python preview_cards_db.py

Connects to DATABASE_URL from your .env file, pulls a sample of real recipes
with resolved images and generated steps, and renders them through the flow
card template.

Flags (env vars):
    LIMIT=10         Number of recipes to render (default 5)
    CUISINE=Asian    Filter to a specific cuisine
    SOURCE=youtube   Filter to "youtube" or "reddit"
    FLOW=0           Use two-column layout instead of flow layout

Output:
    preview_cards_db.pdf

Edit app/templates/recipe_card_flow.html and re-run to iterate.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe, Ingredient, RecipeComponent
from app.card_renderer import _macro_pct, DIFFICULTY_COLORS, DIETARY_ABBR
from app.pdf_renderer import _render_with_playwright
from jinja2 import Environment, FileSystemLoader

LIMIT   = int(os.getenv("LIMIT", "5"))
CUISINE = os.getenv("CUISINE", "")
SOURCE  = os.getenv("SOURCE", "")
USE_FLOW = os.getenv("FLOW", "1") == "1"

engine = create_engine(settings.database_url)

# ---------------------------------------------------------------------------
# Query recipes
# ---------------------------------------------------------------------------

with Session(engine) as db:
    q = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_image_url.isnot(None),
            RawRecipe.card_image_url != "unavailable",
            RawRecipe.card_steps.isnot(None),
            RawRecipe.quick_steps.isnot(None),  # fully classified
        )
    )
    if CUISINE:
        q = q.filter(RawRecipe.cuisine.ilike(f"%{CUISINE}%"))
    if SOURCE:
        q = q.filter(RawRecipe.source == SOURCE)

    raw_recipes = q.limit(LIMIT).all()

    if not raw_recipes:
        print("No recipes found matching filters. Try relaxing CUISINE / SOURCE.")
        sys.exit(1)

    print(f"Found {len(raw_recipes)} recipes — building cards…")

    # Fetch ingredients and components in bulk
    recipe_ids = [r.id for r in raw_recipes]

    ing_rows = (
        db.query(Ingredient)
        .filter(Ingredient.recipe_id.in_(recipe_ids))
        .all()
    )
    ing_map: dict[int, list[dict]] = {rid: [] for rid in recipe_ids}
    for ing in ing_rows:
        ing_map[ing.recipe_id].append({
            "name": ing.ingredient_name,
            "qty":  ing.quantity or "",
            "unit": ing.unit or "",
        })

    comp_rows = (
        db.query(RecipeComponent)
        .filter(RecipeComponent.recipe_id.in_(recipe_ids))
        .order_by(RecipeComponent.recipe_id, RecipeComponent.display_order)
        .all()
    )
    comp_map: dict[int, list[dict]] = {rid: [] for rid in recipe_ids}
    for comp in comp_rows:
        comp_map[comp.recipe_id].append({
            "role":  comp.role,
            "label": comp.label,
        })

    # ---------------------------------------------------------------------------
    # Build recipe dicts for the template
    # ---------------------------------------------------------------------------

    recipes: list[dict] = []
    for r in raw_recipes:
        dietary_tags = json.loads(r.dietary_tags) if r.dietary_tags else []
        card_steps   = json.loads(r.card_steps)   if r.card_steps   else []
        quick_steps  = json.loads(r.quick_steps)  if r.quick_steps  else []

        recipes.append({
            "title":        "",                        # no title column in DB
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
            "ingredients":  ing_map.get(r.id, []),
            "components":   comp_map.get(r.id, []),
            "macros":       {},                        # not yet in DB
            "macro_pct":    _macro_pct({}),
        })

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

template_name = "recipe_card_flow.html" if USE_FLOW else "recipe_card.html"
_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "app" / "templates")),
    autoescape=True,
)
tmpl = _env.get_template(template_name)
html = tmpl.render(
    recipes=recipes,
    difficulty_colors=DIFFICULTY_COLORS,
    dietary_abbr=DIETARY_ABBR,
)

OUTPUT = Path(__file__).parent / "preview_cards_db.pdf"
print(f"Rendering {len(recipes)} cards via {template_name}…")
try:
    pdf_bytes = _render_with_playwright(html, week_label="Recipe Cards")
    OUTPUT.write_bytes(pdf_bytes)
    print(f"Done — {len(pdf_bytes) // 1024} KB written to {OUTPUT}")
    print()
    print(f"Open with:  xdg-open {OUTPUT.name}")
    print()
    print("Filter options:")
    print("  LIMIT=10 python preview_cards_db.py")
    print("  CUISINE=Italian python preview_cards_db.py")
    print("  SOURCE=youtube python preview_cards_db.py")
    print("  FLOW=0 python preview_cards_db.py   # two-column layout")
except Exception as exc:
    print(f"ERROR: {exc}")
    raise

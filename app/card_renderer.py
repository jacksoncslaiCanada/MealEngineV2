"""Recipe card renderer: DALL-E 3 food image + Claude macro estimation + Playwright PDF."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

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


def generate_food_image(title: str, cuisine: str, ingredients: list[dict]) -> str | None:
    """Generate a food photo via DALL-E 3. Returns a base64 data URI or None on failure."""
    try:
        from openai import OpenAI
        from app.config import settings
        if not settings.openai_api_key:
            logger.info("card_renderer: no OpenAI key — skipping image generation")
            return None

        key_ingredients = ", ".join(i["name"] for i in ingredients[:5])
        cuisine_prefix = f"{cuisine} cuisine, " if cuisine else ""

        prompt = (
            f"Professional food photography of {title}. "
            f"{cuisine_prefix}"
            f"Key ingredients visible: {key_ingredients}. "
            f"Shot from a 45-degree overhead angle on a sage green and warm cream linen backdrop. "
            f"Soft natural window light from the left, minimal white ceramic props, "
            f"fresh herbs as garnish, highly appetising, magazine quality, shallow depth of field."
        )

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            response_format="b64_json",
            n=1,
        )
        b64 = response.data[0].b64_json
        return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.warning("card_renderer: image generation failed — %s", exc)
        return None


def estimate_macros(title: str, ingredients: list[dict], servings: int) -> dict:
    """Estimate per-serving macros via Claude Haiku. Returns {cals, protein, carbs, fat}."""
    default: dict = {"cals": 0, "protein": 0, "carbs": 0, "fat": 0}
    try:
        import anthropic
        from app.config import settings
        if not settings.anthropic_api_key:
            return default

        ing_text = ", ".join(
            f"{i.get('qty', '')} {i.get('unit', '')} {i['name']}".strip()
            for i in ingredients
        )

        prompt = (
            f"Estimate nutrition per serving for this recipe: {title}. "
            f"Serves {servings}. Ingredients: {ing_text}. "
            f"Reply ONLY with a JSON object with integer keys: cals, protein, carbs, fat. "
            f'Example: {{"cals": 450, "protein": 35, "carbs": 40, "fat": 12}}'
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return default
    except Exception as exc:
        logger.warning("card_renderer: macro estimation failed — %s", exc)
        return default


def generate_card_steps(raw_content: str, title: str) -> tuple[list[str], str]:
    """Generate 5-6 detailed cooking steps + a chef's tip from raw recipe content.

    Returns (steps_list, tip_string). Falls back to ([], "") on any failure.
    Uses Claude Haiku — call once and cache result in raw_recipes.card_steps / card_tip.
    """
    try:
        import anthropic
        from app.config import settings
        if not settings.anthropic_api_key or not raw_content:
            return [], ""

        prompt = (
            f"You are writing the cooking instructions for a premium recipe card for: {title}.\n\n"
            f"Source material (recipe transcript or post):\n{raw_content[:4000]}\n\n"
            f"Task:\n"
            f"1. Write exactly 5-6 clear, detailed cooking steps. Each step should be 1-2 sentences "
            f"covering a distinct action. Include specific temperatures, timings, and sensory cues "
            f"(e.g. 'until golden brown', 'when the oil shimmers'). Number them 1-6.\n"
            f"2. Write one concise Chef's Tip (max 20 words) — a technique insight, make-ahead note, "
            f"or substitution that genuinely helps.\n\n"
            f"Reply ONLY with valid JSON in this exact shape:\n"
            f'{{"steps": ["step 1...", "step 2...", ...], "tip": "Tip text here."}}'
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            return data.get("steps", []), data.get("tip", "")
        return [], ""
    except Exception as exc:
        logger.warning("card_renderer: card_steps generation failed — %s", exc)
        return [], ""


def _macro_pct(macros: dict) -> dict:
    """Compute rough calorie-share percentages for the macro bar."""
    p_cals = macros.get("protein", 0) * 4
    c_cals = macros.get("carbs", 0) * 4
    f_cals = macros.get("fat", 0) * 9
    total = p_cals + c_cals + f_cals or 1
    return {
        "protein_pct": round(p_cals / total * 100),
        "carbs_pct":   round(c_cals / total * 100),
        "fat_pct":     round(f_cals / total * 100),
    }


def render_recipe_cards(recipes: list[dict]) -> bytes:
    """Render a list of recipe dicts to a multi-page PDF (one card per page)."""
    from app.pdf_renderer import _render_with_playwright

    enriched = []
    for r in recipes:
        macros = r.get("macros") or {}
        enriched.append({**r, "macro_pct": _macro_pct(macros)})

    tmpl = _env.get_template("recipe_card.html")
    html_str = tmpl.render(
        recipes=enriched,
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )
    return _render_with_playwright(html_str, week_label="Recipe Cards")

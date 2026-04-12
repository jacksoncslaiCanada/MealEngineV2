"""PDF renderer for MealPlan using WeasyPrint + Jinja2."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.db.models import MealPlan

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

DIFFICULTY_COLORS = {
    "easy":    "#28a745",
    "medium":  "#fd7e14",
    "complex": "#dc3545",
}

DIETARY_ABBR = {
    "gluten-free":  "GF",
    "dairy-free":   "DF",
    "vegetarian":   "V",
    "vegan":        "VG",
    "nut-free":     "NF",
}

# ---------------------------------------------------------------------------
# Shopping list categoriser
# ---------------------------------------------------------------------------

_PRODUCE = frozenset({
    "tomato", "tomatoes", "onion", "onions", "carrot", "carrots",
    "broccoli", "spinach", "kale", "lettuce", "cucumber", "bell pepper",
    "zucchini", "courgette", "mushroom", "mushrooms", "celery",
    "potato", "potatoes", "sweet potato", "sweet potatoes",
    "lemon", "lime", "avocado", "corn", "peas", "green beans", "asparagus",
    "eggplant", "aubergine", "cauliflower", "cabbage", "ginger",
    "spring onion", "scallion", "green onion",
    "coriander", "cilantro", "parsley", "basil", "mint", "thyme", "rosemary",
    "apple", "banana", "berries", "strawberry", "blueberry", "cherry",
    "mango", "pineapple", "orange", "grape", "peach", "pear",
    "jalapen", "chilli", "chili", "serrano", "habanero",
})

_PROTEIN = frozenset({
    "chicken", "chicken breast", "chicken thigh", "chicken drumstick",
    "beef", "ground beef", "mince", "steak",
    "pork", "pork belly", "pork chop", "pork loin",
    "lamb", "lamb chop", "lamb shank",
    "salmon", "tuna", "shrimp", "prawns", "fish", "cod", "tilapia",
    "sea bass", "halibut", "scallop", "crab", "lobster",
    "egg", "eggs",
    "tofu", "tempeh",
    "lentil", "lentils", "chickpea", "chickpeas", "black bean", "black beans",
    "kidney bean", "kidney beans", "edamame",
    "turkey", "duck",
    "bacon", "ham", "sausage", "chorizo", "pancetta",
})

_DAIRY = frozenset({
    "milk", "butter", "cheese", "cream", "sour cream",
    "yoghurt", "yogurt", "greek yogurt",
    "heavy cream", "double cream", "whipping cream",
    "cream cheese", "parmesan", "cheddar", "mozzarella",
    "feta", "ricotta", "brie", "gouda", "halloumi",
    "half and half", "creme fraiche",
})

_PANTRY = frozenset({
    "rice", "pasta", "noodle", "noodles", "spaghetti", "penne", "linguine",
    "bread", "tortilla", "pita", "wrap",
    "soy sauce", "tamari", "fish sauce", "oyster sauce", "hoisin sauce",
    "hot sauce", "sriracha", "ketchup", "mustard", "mayonnaise",
    "honey", "maple syrup", "agave",
    "coconut milk", "coconut cream",
    "chicken broth", "beef broth", "vegetable broth", "stock",
    "canned tomatoes", "crushed tomatoes", "diced tomatoes",
    "tomato paste", "tomato sauce", "marinara",
    "miso", "tahini", "peanut butter", "almond butter",
    "oats", "oatmeal", "quinoa", "couscous", "bulgur",
    "can", "canned", "tin",
    "breadcrumb", "breadcrumbs", "panko",
    "worcestershire", "balsamic", "rice wine", "mirin", "sake",
    "coconut aminos", "curry paste", "curry powder",
})


def _categorize_shopping(shopping: list[dict]) -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {
        "Produce": [], "Protein": [], "Dairy": [], "Pantry": [], "Other": [],
    }
    for item in shopping:
        name = item["ingredient"].lower()
        if any(k in name for k in _PRODUCE):
            cats["Produce"].append(item)
        elif any(k in name for k in _PROTEIN):
            cats["Protein"].append(item)
        elif any(k in name for k in _DAIRY):
            cats["Dairy"].append(item)
        elif any(k in name for k in _PANTRY):
            cats["Pantry"].append(item)
        else:
            cats["Other"].append(item)
    return {k: v for k, v in cats.items() if v}


def _short_source(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc
        return host.replace("www.", "")
    except Exception:
        return ""


def _thumbnail_url(url: str | None) -> str | None:
    """Return a YouTube thumbnail URL, or None for non-YouTube sources."""
    if not url:
        return None
    if "youtube.com/watch?v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
        return f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
        return f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
    return None


def _compute_highlights(days: list[dict]) -> list[str]:
    """Derive 2-3 at-a-glance highlights from the week's plan."""
    highlights: list[str] = []

    all_meals = [d.get("breakfast", {}) for d in days] + [d.get("dinner", {}) for d in days]
    prep_times = [m.get("prep_time") for m in all_meals if m.get("prep_time")]
    if prep_times:
        quick = sum(1 for t in prep_times if t <= 25)
        if quick >= 5:
            highlights.append(f"{quick} meals in 25 min or less")
        elif quick >= 3:
            highlights.append(f"{quick} quick meals this week")

    cuisines = {
        d.get("dinner", {}).get("cuisine", "").strip()
        for d in days
        if d.get("dinner", {}).get("cuisine", "").strip()
    }
    if len(cuisines) >= 3:
        highlights.append(f"{len(cuisines)} different cuisines")
    elif len(cuisines) == 2:
        highlights.append(" & ".join(sorted(cuisines)))

    spice_levels = [d.get("dinner", {}).get("spice_level") for d in days]
    mild_count = sum(1 for s in spice_levels if s in ("mild", None, ""))
    if mild_count == 7:
        highlights.append("All mild & family-friendly")

    if not highlights:
        highlights.append("7 family dinners ready to go")

    return highlights[:3]


def _generate_intro(days: list[dict], variant_label: str) -> str:
    """Generate a warm 1-2 sentence intro using Claude Haiku. Returns '' on any failure."""
    try:
        from app.config import settings
        import anthropic
        if not settings.anthropic_api_key:
            return ""

        dinners = [
            d["dinner"]["title"]
            for d in days
            if d.get("dinner", {}).get("recipe_id") and d["dinner"].get("title")
        ]
        cuisines = list({
            d["dinner"].get("cuisine", "")
            for d in days
            if d.get("dinner", {}).get("cuisine", "")
        })

        prompt = (
            f"Write a warm, friendly 1-2 sentence intro for a family meal plan newsletter. "
            f"Plan type: {variant_label}. "
            f"This week's dinners: {', '.join(dinners[:5])}. "
            f"Cuisines: {', '.join(c for c in cuisines if c) or 'varied'}. "
            f"Keep it under 35 words. Sound like a friendly meal planning coach. No emojis."
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        logger.warning("pdf_renderer: intro generation failed — %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render_pdf(plan: MealPlan, *, days: list[dict] | None = None) -> bytes:
    """Render a MealPlan to PDF bytes."""
    from app.planner import VARIANTS

    if days is None:
        days = json.loads(plan.plan_json)
    shopping: list[dict] = json.loads(plan.shopping_json)
    variant_label = VARIANTS.get(plan.variant, plan.variant)

    shopping_by_cat = _categorize_shopping(shopping)
    highlights = _compute_highlights(days)
    intro_text = _generate_intro(days, variant_label)

    tmpl = _env.get_template("meal_plan_pdf.html")
    html_str = tmpl.render(
        week_label=plan.week_label,
        variant=plan.variant,
        variant_label=variant_label,
        days=days,
        shopping_by_cat=shopping_by_cat,
        shopping_total=len(shopping),
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
        short_source=_short_source,
        thumbnail_url=_thumbnail_url,
        highlights=highlights,
        intro_text=intro_text,
    )

    return HTML(string=html_str).write_pdf()

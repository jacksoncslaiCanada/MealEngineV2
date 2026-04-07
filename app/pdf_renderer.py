"""PDF renderer for MealPlan using WeasyPrint + Jinja2."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.db.models import MealPlan

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

DIFFICULTY_COLORS = {
    "easy":    "#28a745",
    "medium":  "#fd7e14",
    "complex": "#dc3545",
}

# Abbreviated dietary tag labels for compact display (day grid)
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
    """Assign each shopping item to Produce / Protein / Dairy / Pantry / Other.

    Categories are checked in order — first match wins. Empty categories
    are omitted from the result.
    """
    cats: dict[str, list[dict]] = {
        "Produce": [],
        "Protein": [],
        "Dairy": [],
        "Pantry": [],
        "Other": [],
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
    """Return a compact domain string from a URL, or empty string."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc
        return host.replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Main render entry point
# ---------------------------------------------------------------------------

def render_pdf(plan: MealPlan, *, days: list[dict] | None = None) -> bytes:
    """Render a MealPlan to PDF bytes.

    Pass ``days`` to use pre-enriched day data (with live classifier fields);
    otherwise falls back to what is stored in plan.plan_json.
    """
    from app.planner import VARIANTS

    if days is None:
        days = json.loads(plan.plan_json)
    shopping: list[dict] = json.loads(plan.shopping_json)
    variant_label = VARIANTS.get(plan.variant, plan.variant)

    shopping_by_cat = _categorize_shopping(shopping)

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
    )

    return HTML(string=html_str).write_pdf()

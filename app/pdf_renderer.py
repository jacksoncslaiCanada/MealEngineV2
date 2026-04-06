"""PDF renderer for MealPlan using WeasyPrint + Jinja2."""
from __future__ import annotations

import json
from pathlib import Path

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


def render_pdf(plan: MealPlan, *, days: list[dict] | None = None) -> bytes:
    """Render a MealPlan to PDF bytes.

    Pass ``days`` to use pre-enriched day data (with live quick_steps);
    otherwise falls back to what is stored in plan.plan_json.
    """
    from app.planner import VARIANTS

    if days is None:
        days = json.loads(plan.plan_json)
    shopping: list[dict] = json.loads(plan.shopping_json)
    variant_label = VARIANTS.get(plan.variant, plan.variant)

    # Split shopping into two columns for the PDF
    mid = (len(shopping) + 1) // 2
    shopping_col1 = shopping[:mid]
    shopping_col2 = shopping[mid:]

    tmpl = _env.get_template("meal_plan_pdf.html")
    html_str = tmpl.render(
        week_label=plan.week_label,
        variant=plan.variant,
        variant_label=variant_label,
        days=days,
        shopping_col1=shopping_col1,
        shopping_col2=shopping_col2,
        difficulty_colors=DIFFICULTY_COLORS,
    )

    return HTML(string=html_str).write_pdf()

"""Meal plan API routes."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.classifier import classify_unclassified
from app.db.models import Ingredient, MealPlan, RawRecipe
from app.db.session import get_db
from app.pdf_renderer import render_pdf
from app.planner import VARIANTS, generate_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["plans"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PlanSummary(BaseModel):
    id: int
    variant: str
    variant_label: str
    week_label: str
    created_at: str
    has_pdf: bool

    model_config = {"from_attributes": True}


class PlanDetail(PlanSummary):
    days: list[dict]
    shopping: list[dict]


# ---------------------------------------------------------------------------
# Live quick_steps enrichment
# ---------------------------------------------------------------------------

def _enrich_days(days: list[dict], db: Session) -> list[dict]:
    """Replace classifier fields in each day entry with live values from the DB.

    This decouples all Phase A metadata from the cached plan_json so that as
    the background classifier populates recipes, any plan view picks up the
    latest data without regenerating the plan.
    """
    recipe_ids = set()
    for day in days:
        for slot in ("breakfast", "dinner"):
            rid = day.get(slot, {}).get("recipe_id")
            if rid:
                recipe_ids.add(rid)

    if not recipe_ids:
        return days

    rows = (
        db.query(
            RawRecipe.id,
            RawRecipe.quick_steps,
            RawRecipe.prep_time,
            RawRecipe.dietary_tags,
            RawRecipe.spice_level,
            RawRecipe.servings,
            RawRecipe.url,
        )
        .filter(RawRecipe.id.in_(recipe_ids))
        .all()
    )
    recipe_map: dict[int, dict] = {}
    for rid, qs, prep_time, dietary_tags, spice_level, servings, url in rows:
        recipe_map[rid] = {
            "quick_steps": json.loads(qs) if qs else [],
            "prep_time": prep_time,
            "dietary_tags": json.loads(dietary_tags) if dietary_tags else [],
            "spice_level": spice_level or "mild",
            "servings": servings,
            "url": url,
            "ingredients": [],
        }

    # Fetch per-recipe ingredient lists
    ing_rows = (
        db.query(
            Ingredient.recipe_id,
            Ingredient.ingredient_name,
            Ingredient.quantity,
            Ingredient.unit,
        )
        .filter(Ingredient.recipe_id.in_(recipe_ids))
        .all()
    )
    for recipe_id, name, qty, unit in ing_rows:
        if recipe_id in recipe_map:
            recipe_map[recipe_id]["ingredients"].append({
                "name": name,
                "qty": qty or "",
                "unit": unit or "",
            })

    enriched = []
    for day in days:
        day = dict(day)
        for slot in ("breakfast", "dinner"):
            if slot in day and day[slot].get("recipe_id"):
                day[slot] = dict(day[slot])
                data = recipe_map.get(day[slot]["recipe_id"], {})
                day[slot].update(data)
        enriched.append(day)

    return enriched


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/variants")
def list_variants() -> dict[str, str]:
    return VARIANTS


def _run_classify_background(db: Session) -> None:
    try:
        n = classify_unclassified(db, limit=30)
        if n:
            logger.info("Background classifier: classified %d recipe(s)", n)
    except Exception as exc:
        logger.warning("Background classification failed: %s", exc)
    finally:
        db.close()


@router.post("/generate", response_model=PlanDetail)
@limiter.limit("6/hour")
def generate(
    request: Request,
    background_tasks: BackgroundTasks,
    variant: str = Query(..., description="One of: " + ", ".join(VARIANTS)),
    week_label: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if variant not in VARIANTS:
        raise HTTPException(400, f"Unknown variant. Choose from: {list(VARIANTS)}")

    try:
        classify_unclassified(db, limit=5)
    except Exception as exc:
        logger.warning("Sync classification failed (continuing): %s", exc)

    from app.db.session import SessionLocal
    bg_db = SessionLocal()
    background_tasks.add_task(_run_classify_background, bg_db)

    try:
        plan = generate_plan(db, variant=variant, week_label=week_label)
    except Exception as exc:
        logger.exception("Plan generation failed")
        raise HTTPException(500, str(exc)) from exc

    return _to_detail(plan, db)


@router.get("", response_model=list[PlanSummary])
def list_plans(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    plans = (
        db.query(MealPlan)
        .order_by(MealPlan.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_to_summary(p) for p in plans]


@router.get("/{plan_id}", response_model=PlanDetail)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(MealPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    return _to_detail(plan, db)


@router.post("/{plan_id}/classify")
def classify_plan_recipes(plan_id: int, db: Session = Depends(get_db)):
    """Force-classify every recipe in this plan and return results."""
    plan = db.get(MealPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    days = json.loads(plan.plan_json)
    recipe_ids = []
    for day in days:
        for slot in ("breakfast", "dinner"):
            rid = day.get(slot, {}).get("recipe_id")
            if rid:
                recipe_ids.append(rid)

    if not recipe_ids:
        return {"classified": 0, "errors": [], "detail": "No recipe_ids found in plan"}

    recipes = db.query(RawRecipe).filter(RawRecipe.id.in_(set(recipe_ids))).all()

    import anthropic as _anthropic
    from app.classifier import classify_recipe
    from app.config import settings

    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    results = {"classified": 0, "skipped": 0, "errors": []}

    for recipe in recipes:
        try:
            before = recipe.quick_steps
            # Force re-classify if quick_steps missing
            if not recipe.quick_steps:
                recipe.difficulty = None  # reset so classifier doesn't short-circuit
                db.commit()
            classify_recipe(db, recipe, client=client)
            if recipe.quick_steps:
                results["classified"] += 1
            else:
                results["skipped"] += 1
        except Exception as exc:
            results["errors"].append({"recipe_id": recipe.id, "error": str(exc)})
            logger.exception("classify_plan_recipes: recipe %d failed", recipe.id)

    return results


@router.get("/{plan_id}/pdf")
def download_pdf(plan_id: int, db: Session = Depends(get_db)):
    """Return PDF, regenerating it so quick_steps are always current."""
    plan = db.get(MealPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Always re-render so the PDF picks up the latest quick_steps from DB
    try:
        days = _enrich_days(json.loads(plan.plan_json), db)
        pdf_bytes = render_pdf(plan, days=days)
        plan.pdf_data = pdf_bytes
        db.commit()
    except Exception as exc:
        logger.exception("PDF render failed for plan %d", plan_id)
        raise HTTPException(500, f"PDF generation failed: {exc}") from exc

    filename = f"meal-plan-{plan.week_label}-{plan.variant}.pdf"
    return Response(
        content=plan.pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_summary(plan: MealPlan) -> PlanSummary:
    return PlanSummary(
        id=plan.id,
        variant=plan.variant,
        variant_label=VARIANTS.get(plan.variant, plan.variant),
        week_label=plan.week_label,
        created_at=plan.created_at.isoformat(),
        has_pdf=plan.pdf_data is not None,
    )


def _to_detail(plan: MealPlan, db: Session) -> PlanDetail:
    s = _to_summary(plan)
    days = _enrich_days(json.loads(plan.plan_json), db)
    return PlanDetail(
        **s.model_dump(),
        days=days,
        shopping=json.loads(plan.shopping_json),
    )

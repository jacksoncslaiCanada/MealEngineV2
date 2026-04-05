"""Meal plan API routes."""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.classifier import classify_unclassified
from app.db.models import MealPlan
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
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/variants")
def list_variants() -> dict[str, str]:
    """Return all available plan variants."""
    return VARIANTS


@router.post("/generate", response_model=PlanDetail)
def generate(
    variant: str = Query(..., description="One of: " + ", ".join(VARIANTS)),
    week_label: Optional[str] = Query(None, description="e.g. 2024-W15 (defaults to current week)"),
    classify_first: bool = Query(True, description="Run classifier on unclassified recipes before planning"),
    db: Session = Depends(get_db),
):
    """Classify recipes (if needed), generate a 7-day meal plan, and return it."""
    if variant not in VARIANTS:
        raise HTTPException(400, f"Unknown variant. Choose from: {list(VARIANTS)}")

    if classify_first:
        try:
            n = classify_unclassified(db, limit=200)
            if n:
                logger.info("Classified %d recipe(s) before planning", n)
        except Exception as exc:
            logger.warning("Classification step failed (continuing): %s", exc)

    try:
        plan = generate_plan(db, variant=variant, week_label=week_label)
    except Exception as exc:
        logger.exception("Plan generation failed")
        raise HTTPException(500, str(exc)) from exc

    return _to_detail(plan)


@router.get("", response_model=list[PlanSummary])
def list_plans(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List recent meal plans, newest first."""
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
    return _to_detail(plan)


@router.get("/{plan_id}/pdf")
def download_pdf(plan_id: int, db: Session = Depends(get_db)):
    """Return the PDF for this plan, generating it on first request."""
    plan = db.get(MealPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")

    if not plan.pdf_data:
        try:
            pdf_bytes = render_pdf(plan)
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
    from app.planner import VARIANTS
    return PlanSummary(
        id=plan.id,
        variant=plan.variant,
        variant_label=VARIANTS.get(plan.variant, plan.variant),
        week_label=plan.week_label,
        created_at=plan.created_at.isoformat(),
        has_pdf=plan.pdf_data is not None,
    )


def _to_detail(plan: MealPlan) -> PlanDetail:
    s = _to_summary(plan)
    return PlanDetail(
        **s.model_dump(),
        days=json.loads(plan.plan_json),
        shopping=json.loads(plan.shopping_json),
    )

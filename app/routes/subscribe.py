"""Subscribe page — lets Gumroad buyers register for weekly email delivery."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.models import MealPlan, Subscriber
from app.db.session import get_db
from app.planner import VARIANTS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscribe"])
templates = Jinja2Templates(directory="app/templates")

# Valid variants buyers can subscribe to
_PUBLIC_VARIANTS = {"little_ones", "teen_table"}


def _latest_plan_for_variant(db: Session, variant: str) -> MealPlan | None:
    """Return the most recently generated plan for this variant, or None."""
    return (
        db.query(MealPlan)
        .filter(MealPlan.variant == variant)
        .order_by(MealPlan.created_at.desc())
        .first()
    )


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe_page(
    request: Request,
    variant: str = "",
    db: Session = Depends(get_db),
):
    """Render the subscribe landing page. ?variant= pre-selects a plan type."""
    prefill = variant if variant in _PUBLIC_VARIANTS else ""
    return templates.TemplateResponse(
        "subscribe.html",
        {
            "request": request,
            "prefill_variant": prefill,
            "prefill_email": "",
            "success": False,
            "error": None,
            "variant_error": False,
        },
    )


@router.post("/subscribe", response_class=HTMLResponse)
def subscribe_submit(
    request: Request,
    email: str = Form(...),
    variant: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Handle subscribe form submission."""
    from app.email_sender import send_welcome_email
    from app.pdf_renderer import render_pdf
    from app.routes.plans import _enrich_days

    # ── Validate inputs ──────────────────────────────────────────────────
    email = email.strip().lower()
    variant = variant.strip()

    if not email or "@" not in email:
        return templates.TemplateResponse(
            "subscribe.html",
            {
                "request": request,
                "prefill_variant": variant,
                "prefill_email": email,
                "success": False,
                "error": "Please enter a valid email address.",
                "variant_error": False,
            },
        )

    if variant not in _PUBLIC_VARIANTS:
        return templates.TemplateResponse(
            "subscribe.html",
            {
                "request": request,
                "prefill_variant": "",
                "prefill_email": email,
                "success": False,
                "error": None,
                "variant_error": True,
            },
        )

    # ── Check for existing subscriber ────────────────────────────────────
    existing = db.query(Subscriber).filter(Subscriber.email == email).first()

    if existing:
        if existing.variant != variant:
            # Different variant — update it and reactivate
            existing.variant = variant
            existing.active = True
            if existing.plans_remaining == 0:
                existing.plans_remaining = 4
            db.commit()
            logger.info("subscribe: updated variant for %s → %s", email, variant)
        elif not existing.active:
            # Re-activating a lapsed subscriber
            existing.active = True
            existing.plans_remaining = 4
            db.commit()
            logger.info("subscribe: reactivated %s", email)
        else:
            # Already active — still show success, resend welcome
            logger.info("subscribe: already active %s — resending welcome", email)
    else:
        # New subscriber
        sub = Subscriber(
            email=email,
            variant=variant,
            plans_remaining=4,
            active=True,
            purchased_at=datetime.now(timezone.utc),
        )
        db.add(sub)
        try:
            db.commit()
            logger.info("subscribe: new subscriber %s (%s)", email, variant)
        except Exception as exc:
            db.rollback()
            logger.error("subscribe: DB error for %s — %s", email, exc)
            return templates.TemplateResponse(
                "subscribe.html",
                {
                    "request": request,
                    "prefill_variant": variant,
                    "prefill_email": email,
                    "success": False,
                    "error": "Something went wrong. Please try again.",
                    "variant_error": False,
                },
            )

    # ── Send welcome email with this week's PDF ───────────────────────────
    variant_label = VARIANTS.get(variant, variant)
    plan = _latest_plan_for_variant(db, variant)

    pdf_bytes: bytes | None = None
    week_label = ""

    if plan:
        week_label = plan.week_label
        try:
            days = _enrich_days(json.loads(plan.plan_json), db)
            pdf_bytes = render_pdf(plan, days=days)
        except Exception as exc:
            logger.warning("subscribe: could not render welcome PDF — %s", exc)

    try:
        send_welcome_email(
            to_email=email,
            variant_label=variant_label,
            week_label=week_label,
            pdf_bytes=pdf_bytes,
        )
    except Exception as exc:
        logger.warning("subscribe: welcome email failed for %s — %s", email, exc)

    return templates.TemplateResponse(
        "subscribe.html",
        {
            "request": request,
            "prefill_variant": variant,
            "prefill_email": email,
            "success": True,
            "error": None,
            "variant_error": False,
        },
    )

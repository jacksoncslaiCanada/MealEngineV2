"""Internal cron routes — called by Railway's cron scheduler.

All endpoints are protected by a shared secret (X-Cron-Secret header)
set as a Railway environment variable. They are not rate-limited because
they are only called by the scheduler, not end users.
"""
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Subscriber
from app.db.session import get_db
from app.email_sender import send_conversion_email, send_plan_email
from app.gumroad import update_product_file
from app.pdf_renderer import render_pdf
from app.planner import VARIANTS, generate_plan
from app.routes.plans import _enrich_days
from app.storage import upload_pdf

import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# Variants published each week on Gumroad + emailed to subscribers
_WEEKLY_VARIANTS = ["little_ones", "teen_table"]


def _require_cron_secret(x_cron_secret: str = Header(default="")) -> None:
    """Dependency: reject requests missing the correct cron secret."""
    if not settings.cron_secret:
        raise HTTPException(500, "CRON_SECRET not configured on server")
    if x_cron_secret != settings.cron_secret:
        raise HTTPException(403, "Invalid cron secret")


@router.post("/weekly-run")
def weekly_run(_: None = Depends(_require_cron_secret)):
    """
    Saturday morning cron job. For each weekly variant:
      1. Generate a fresh meal plan PDF
      2. Upload to Supabase Storage
      3. Update the Gumroad product file
      4. Email all active subscribers who have plans remaining
      5. Email conversion nudge to subscribers at zero plans

    Each variant gets its own DB session so a failure in one cannot
    leave the session in a broken state for the next variant.
    """
    from app.db.session import SessionLocal

    today = date.today()
    year, week, _ = today.isocalendar()
    week_label = f"{year}-W{week:02d}"

    results: dict = {}

    for variant in _WEEKLY_VARIANTS:
        variant_label = VARIANTS.get(variant, variant)
        logger.info("weekly_run: generating %s for %s", variant, week_label)
        variant_result: dict = {
            "plan_id": None,
            "storage_url": None,
            "gumroad_updated": False,
            "emails_sent": 0,
            "conversion_emails_sent": 0,
            "errors": [],
        }

        db = SessionLocal()
        try:
            # ── 1. Generate plan ──────────────────────────────────────────
            try:
                plan = generate_plan(db, variant=variant, week_label=week_label)
                variant_result["plan_id"] = plan.id
            except Exception as exc:
                logger.exception("weekly_run: plan generation failed for %s", variant)
                variant_result["errors"].append(f"plan_generation: {exc}")
                results[variant] = variant_result
                continue

            # ── 2. Render PDF with enriched days ──────────────────────────
            try:
                days = _enrich_days(json.loads(plan.plan_json), db)
                pdf_bytes = render_pdf(plan, days=days)
                plan.pdf_data = pdf_bytes
                db.commit()
            except Exception as exc:
                logger.exception("weekly_run: PDF render failed for %s", variant)
                variant_result["errors"].append(f"pdf_render: {exc}")
                results[variant] = variant_result
                continue

            # ── 3. Upload to Supabase Storage ─────────────────────────────
            try:
                url = upload_pdf(pdf_bytes, variant=variant, week_label=week_label)
                variant_result["storage_url"] = url
            except Exception as exc:
                logger.warning("weekly_run: storage upload failed for %s — %s", variant, exc)
                variant_result["errors"].append(f"storage_upload: {exc}")

            # ── 4. Update Gumroad product file ────────────────────────────
            try:
                ok = update_product_file(pdf_bytes, variant=variant, week_label=week_label)
                variant_result["gumroad_updated"] = ok
            except Exception as exc:
                logger.warning("weekly_run: Gumroad update failed for %s — %s", variant, exc)
                variant_result["errors"].append(f"gumroad_update: {exc}")

            # ── 5. Email subscribers ──────────────────────────────────────
            subscribers = (
                db.query(Subscriber)
                .filter(
                    Subscriber.variant == variant,
                    Subscriber.active == True,
                )
                .all()
            )

            for sub in subscribers:
                try:
                    if sub.plans_remaining > 0:
                        ok = send_plan_email(
                            to_email=sub.email,
                            variant_label=variant_label,
                            week_label=week_label,
                            pdf_bytes=pdf_bytes,
                            plans_remaining=sub.plans_remaining,
                        )
                        if ok:
                            sub.plans_remaining -= 1
                            sub.last_sent_at = datetime.now(timezone.utc)
                            variant_result["emails_sent"] += 1
                    else:
                        ok = send_conversion_email(
                            to_email=sub.email,
                            variant_label=variant_label,
                        )
                        if ok:
                            sub.active = False
                            variant_result["conversion_emails_sent"] += 1

                except Exception as exc:
                    logger.warning("weekly_run: email failed for %s — %s", sub.email, exc)
                    variant_result["errors"].append(f"email:{sub.email}: {exc}")

            try:
                db.commit()
            except Exception as exc:
                logger.error("weekly_run: DB commit failed after emails for %s — %s", variant, exc)
                db.rollback()
                variant_result["errors"].append(f"db_commit: {exc}")

        finally:
            db.close()

        results[variant] = variant_result
        logger.info(
            "weekly_run: %s done — emails=%d conversions=%d errors=%d",
            variant,
            variant_result["emails_sent"],
            variant_result["conversion_emails_sent"],
            len(variant_result["errors"]),
        )

    return {"week_label": week_label, "results": results}


@router.post("/weekly-run/dry-run")
def weekly_run_dry(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """Generate plans and render PDFs without sending emails or updating Gumroad.
    Use this to verify the pipeline before the first live run.
    """
    today = date.today()
    year, week, _ = today.isocalendar()
    week_label = f"{year}-W{week:02d}"

    results = {}
    for variant in _WEEKLY_VARIANTS:
        try:
            plan = generate_plan(db, variant=variant, week_label=week_label)
            days = _enrich_days(json.loads(plan.plan_json), db)
            pdf_bytes = render_pdf(plan, days=days)
            results[variant] = {
                "plan_id": plan.id,
                "pdf_bytes": len(pdf_bytes),
                "status": "ok",
            }
        except Exception as exc:
            logger.exception("dry_run: failed for %s", variant)
            results[variant] = {"status": "error", "detail": str(exc)}

    return {"week_label": week_label, "dry_run": True, "results": results}

"""Internal cron routes — called by Railway's cron scheduler.

All endpoints are protected by a shared secret (X-Cron-Secret header)
set as a Railway environment variable. They are not rate-limited because
they are only called by the scheduler, not end users.
"""
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Subscriber
from app.db.session import get_db
from app.classifier import classify_unclassified
from app.email_sender import send_conversion_email, send_plan_email
from app.gumroad import update_product_url
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


@router.post("/classify-backlog")
def classify_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 200,
):
    """
    One-shot endpoint to classify unclassified recipes in bulk.

    Call this from the Swagger UI (/docs) to clear the backlog.
    Safe to call multiple times — already-classified recipes are skipped.
    Default limit=200; call repeatedly until it returns classified=0.
    """
    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    classified = classify_unclassified(db, client=client, limit=limit)
    return {"classified": classified, "limit": limit}


@router.post("/classify-components-backlog")
def classify_components_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 100,
):
    """
    One-shot endpoint to populate recipe_components for all classified recipes.

    Call repeatedly (default limit=100) until it returns {"saved": 0}.
    Already-processed recipes are skipped automatically.
    """
    import anthropic as _anthropic
    from app.classifier import classify_unclassified_components
    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    saved = classify_unclassified_components(db, client=client, limit=limit)
    return {"saved": saved, "limit": limit}


@router.post("/generate-card-steps-backlog")
def generate_card_steps_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 50,
):
    """
    Generate detailed card_steps + card_tip for recipes that don't have them yet.

    Uses Claude Haiku to produce 5-6 detailed cooking steps and a chef's tip from
    each recipe's raw_content. Results are cached in raw_recipes.card_steps / card_tip.
    Call repeatedly until it returns {"saved": 0}.
    """
    import json as _json
    import anthropic as _anthropic
    from app.db.models import RawRecipe
    from app.card_renderer import generate_card_steps

    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)

    rows = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_steps.is_(None),
            RawRecipe.raw_content.isnot(None),
            RawRecipe.quick_steps.isnot(None),  # only classified recipes
        )
        .limit(limit)
        .all()
    )

    from app.card_renderer import _extract_title

    saved = 0
    for recipe in rows:
        try:
            title = getattr(recipe, "title", None) or _extract_title(recipe.raw_content or "")
            steps, tip, summary = generate_card_steps(recipe.raw_content, title)
            if steps:
                recipe.card_steps = _json.dumps(steps)
                recipe.card_tip = tip
                recipe.card_summary = summary
                saved += 1
        except Exception as exc:
            logger.warning("card_steps backlog: recipe %s failed — %s", recipe.id, exc)

    if saved:
        db.commit()

    return {"saved": saved, "limit": limit}


@router.post("/resolve-card-images-backlog")
def resolve_card_images_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 20,
    retry_unavailable: bool = False,
):
    """
    Resolve and store card images for recipes that don't have one yet.

    For each recipe:
      - Uses the YouTube thumbnail if it's a real image (not placeholder)
      - Falls back to Flux Schnell generation via Replicate (~$0.003/image)
    Images are uploaded to the Supabase recipe-images bucket and the URL
    is cached in raw_recipes.card_image_url.

    Keep limit low (default 20) since each Flux call takes ~5-10s.
    Call repeatedly until {"saved": 0, "attempted": 0}.

    retry_unavailable=true  Re-processes recipes previously marked "unavailable"
                            (e.g. after fixing a missing API key or network issue).

    Prerequisites:
      - REPLICATE_API_KEY set in Railway env vars (for Flux fallback)
      - SUPABASE_URL + SUPABASE_SERVICE_KEY configured
      - recipe-images bucket created in Supabase Storage (set to public)
    """
    from app.db.models import RawRecipe
    from app.card_renderer import resolve_card_image, _extract_title

    if retry_unavailable:
        rows = (
            db.query(RawRecipe)
            .filter(RawRecipe.card_image_url == "unavailable")
            .limit(limit)
            .all()
        )
    else:
        rows = (
            db.query(RawRecipe)
            .filter(RawRecipe.card_image_url.is_(None))
            .limit(limit)
            .all()
        )

    saved = 0
    for recipe in rows:
        ingredients = [
            {"name": ing.ingredient_name, "qty": ing.quantity or "", "unit": ing.unit or ""}
            for ing in recipe.ingredients
        ]
        title = getattr(recipe, "title", None) or _extract_title(recipe.raw_content or "")
        url = resolve_card_image(
            recipe_id=recipe.id,
            title=title,
            cuisine=recipe.cuisine or "",
            ingredients=ingredients,
            source_url=recipe.url,
        )
        if url:
            recipe.card_image_url = url
            saved += 1
        else:
            recipe.card_image_url = "unavailable"

    if rows:
        db.commit()

    return {"saved": saved, "attempted": len(rows), "limit": limit, "retry_unavailable": retry_unavailable}


@router.get("/gumroad-check")
def gumroad_check(_: None = Depends(_require_cron_secret)):
    """Diagnose Gumroad API connectivity and product ID validity."""
    import httpx
    from app.gumroad import _product_id_for_variant

    results = {}
    for variant in ["little_ones", "teen_table"]:
        product_id = _product_id_for_variant(variant)
        if not product_id:
            results[variant] = {"error": "no product ID configured in Railway"}
            continue
        try:
            resp = httpx.get(
                f"https://api.gumroad.com/v2/products/{product_id}",
                params={"access_token": settings.gumroad_access_token},
                timeout=10,
            )
            results[variant] = {
                "product_id": product_id,
                "status": resp.status_code,
                "body": resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text[:300],
            }
        except Exception as exc:
            results[variant] = {"product_id": product_id, "error": str(exc)}
    return results


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

            # ── 4. Update Gumroad delivery URL ────────────────────────────
            # Only update if we have a storage URL to point to
            if variant_result["storage_url"]:
                try:
                    ok = update_product_url(
                        variant=variant,
                        storage_url=variant_result["storage_url"],
                    )
                    variant_result["gumroad_updated"] = ok
                except Exception as exc:
                    logger.warning("weekly_run: Gumroad update failed for %s — %s", variant, exc)
                    variant_result["errors"].append(f"gumroad_update: {exc}")
            else:
                logger.warning("weekly_run: skipping Gumroad update for %s — no storage URL", variant)
                variant_result["errors"].append("gumroad_update: skipped, no storage_url")

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


@router.get("/preview-card")
def preview_card(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    recipe_id: int | None = None,
):
    """
    Render a single recipe card as a PDF and return it for download.

    Useful for checking card design with real data without generating a full weekly plan.
    Picks the first fully-populated recipe if no recipe_id is given.

    Query params:
        recipe_id=123   Render a specific recipe (optional)
    """
    import json as _json
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader
    from app.db.models import RawRecipe, Ingredient, RecipeComponent
    from app.card_renderer import _macro_pct, DIFFICULTY_COLORS, DIETARY_ABBR, _extract_title
    from app.pdf_renderer import _render_with_playwright

    q = db.query(RawRecipe).filter(
        RawRecipe.card_image_url.isnot(None),
        RawRecipe.card_image_url != "unavailable",
        RawRecipe.card_steps.isnot(None),
        RawRecipe.quick_steps.isnot(None),
    )
    if recipe_id:
        recipe = q.filter(RawRecipe.id == recipe_id).first()
    else:
        recipe = q.first()

    if not recipe:
        raise HTTPException(404, "No fully-populated recipe found. Run the backlog endpoints first.")

    ingredients = (
        db.query(Ingredient)
        .filter(Ingredient.recipe_id == recipe.id)
        .all()
    )
    components = (
        db.query(RecipeComponent)
        .filter(RecipeComponent.recipe_id == recipe.id)
        .order_by(RecipeComponent.display_order)
        .all()
    )

    dietary_tags = _json.loads(recipe.dietary_tags) if recipe.dietary_tags else []
    card_steps   = _json.loads(recipe.card_steps)   if recipe.card_steps   else []
    quick_steps  = _json.loads(recipe.quick_steps)  if recipe.quick_steps  else []

    title = _extract_title(recipe.raw_content or "") or recipe.cuisine or "Recipe"

    recipe_dict = {
        "title":        title,
        "cuisine":      recipe.cuisine or "",
        "difficulty":   recipe.difficulty or "",
        "prep_time":    recipe.prep_time,
        "servings":     recipe.servings or 4,
        "dietary_tags": dietary_tags,
        "url":          recipe.url,
        "image_url":    recipe.card_image_url,
        "card_steps":   card_steps,
        "quick_steps":  quick_steps,
        "card_tip":     recipe.card_tip or "",
        "card_summary": recipe.card_summary or "",
        "ingredients":  [
            {"name": i.ingredient_name, "qty": i.quantity or "", "unit": i.unit or ""}
            for i in ingredients
        ],
        "components":   [
            {"role": c.role, "label": c.label}
            for c in components
        ],
        "macros":    {},
        "macro_pct": _macro_pct({}),
    }

    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    html = env.get_template("recipe_card_flow.html").render(
        recipes=[recipe_dict],
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )

    pdf_bytes = _render_with_playwright(html, week_label="Recipe Card Preview")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=recipe-card-{recipe.id}.pdf"},
    )

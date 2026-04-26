"""Internal cron routes — called by Railway's cron scheduler.

All endpoints are protected by a shared secret (X-Cron-Secret header)
set as a Railway environment variable. They are not rate-limited because
they are only called by the scheduler, not end users.
"""
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
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


@router.post("/generate-ingredient-quantities-backlog")
def generate_ingredient_quantities_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 20,
):
    """
    Extract missing ingredient quantities from raw recipe content using Claude Haiku.

    Finds recipes where ≥1 ingredient has a NULL quantity AND the recipe has
    extractable content (card_steps or raw_content). Sends context to Claude
    and writes results back to the ingredients table.

    Ingredients Claude cannot determine are marked quantity="" so they are
    excluded from future runs (preventing infinite re-processing loops).
    Only NULL quantities are picked up; "" means "attempted, not found".

    Call repeatedly until {"saved": 0, "marked_attempted": 0}.
    Each call processes up to `limit` recipes (default 20).
    """
    import json as _json
    import anthropic as _anthropic
    from sqlalchemy import or_
    from app.db.models import RawRecipe, Ingredient

    # Only recipes with NULL quantities AND content to extract from.
    # Excludes quantity="" (already attempted) and recipes with no content.
    recipe_ids = [
        row.recipe_id
        for row in (
            db.query(Ingredient.recipe_id)
            .join(RawRecipe, RawRecipe.id == Ingredient.recipe_id)
            .filter(
                Ingredient.quantity.is_(None),
                or_(
                    RawRecipe.card_steps.isnot(None),
                    RawRecipe.raw_content.isnot(None),
                ),
            )
            .distinct()
            .limit(limit)
            .all()
        )
    ]

    if not recipe_ids:
        return {"saved": 0, "marked_attempted": 0, "recipes_processed": 0, "limit": limit}

    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    recipes = db.query(RawRecipe).filter(RawRecipe.id.in_(recipe_ids)).all()

    total_saved = 0
    total_marked = 0
    recipes_updated = 0

    for recipe in recipes:
        missing = (
            db.query(Ingredient)
            .filter(
                Ingredient.recipe_id == recipe.id,
                Ingredient.quantity.is_(None),
            )
            .all()
        )
        if not missing:
            continue

        # Build context: card_steps (concise) + raw_content excerpt
        context_parts = []
        if recipe.card_steps:
            try:
                steps = _json.loads(recipe.card_steps)
                context_parts.append(
                    "COOKING STEPS:\n" + "\n".join(f"- {s}" for s in steps)
                )
            except Exception:
                pass
        if recipe.raw_content:
            context_parts.append(f"SOURCE CONTENT (excerpt):\n{recipe.raw_content[:2500]}")

        if not context_parts:
            # No content — mark all as attempted so they never re-appear
            for ing in missing:
                ing.quantity = ""
            db.commit()
            total_marked += len(missing)
            continue

        title = recipe.card_title or recipe.cuisine or "Recipe"
        ing_list = "\n".join(f'- "{ing.ingredient_name}"' for ing in missing)

        prompt = (
            f"Recipe: {title} (serves {recipe.servings or 4})\n\n"
            + "\n\n".join(context_parts)
            + f"\n\nFind the quantity and unit for each ingredient listed below.\n"
            f"Rules:\n"
            f"- Only use quantities found in the recipe content above.\n"
            f"- For salt, pepper, and spices with no stated amount: "
            f'  return {{"qty": "", "unit": "to taste"}}.\n'
            f"- For oil, butter, and water with no stated amount: "
            f'  return {{"qty": "", "unit": "as needed"}}.\n'
            f"- If a quantity genuinely cannot be determined, return null.\n"
            f"- Prefer standard units: cup, tbsp, tsp, g, kg, ml, l, oz, lb.\n\n"
            f"Ingredients:\n{ing_list}\n\n"
            f"Reply ONLY with valid JSON — no other text:\n"
            f'{{\"ingredient name\": {{\"qty\": \"2\", \"unit\": \"cups\"}} or null}}'
        )

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            start, end = text.find("{"), text.rfind("}") + 1
            data = _json.loads(text[start:end])

            saved = 0
            marked = 0
            for ing in missing:
                result = data.get(ing.ingredient_name)
                if result:
                    qty  = (result.get("qty")  or "").strip()
                    unit = (result.get("unit") or "").strip()
                    # Use "" (not None) as sentinel — None would be re-processed next run
                    ing.quantity = qty if qty else ""
                    ing.unit     = unit or None
                    if qty or unit:
                        saved += 1
                    else:
                        marked += 1  # "to taste" / "as needed" with empty qty
                else:
                    # Claude returned null — mark as attempted so it won't loop
                    ing.quantity = ""
                    marked += 1

            db.commit()
            total_saved  += saved
            total_marked += marked
            if saved or marked:
                recipes_updated += 1
            logger.info(
                "ingredient_quantities: recipe %s — filled=%d marked=%d/%d",
                recipe.id, saved, marked, len(missing),
            )

        except Exception as exc:
            logger.warning("ingredient_quantities: recipe %s failed — %s", recipe.id, exc)

    return {
        "saved": total_saved,
        "marked_attempted": total_marked,
        "recipes_processed": recipes_updated,
        "limit": limit,
    }


@router.post("/generate-titles-backlog")
def generate_titles_backlog(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 100,
):
    """
    Generate clean dish-name titles for recipes that don't have one yet.

    Uses Claude Haiku to produce a 3-6 word dish name stored in card_title.
    Call repeatedly until {"saved": 0}.
    """
    from app.db.models import RawRecipe
    from app.card_renderer import generate_card_title

    rows = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_title.is_(None),
            RawRecipe.quick_steps.isnot(None),   # classified recipes only
        )
        .limit(limit)
        .all()
    )

    saved = 0
    for recipe in rows:
        try:
            title = generate_card_title(
                raw_content=recipe.raw_content or "",
                card_summary=recipe.card_summary or "",
                cuisine=recipe.cuisine or "",
            )
            if title:
                recipe.card_title = title
                saved += 1
        except Exception as exc:
            logger.warning("generate_titles_backlog: recipe %s failed — %s", recipe.id, exc)

    if saved:
        db.commit()

    return {"saved": saved, "limit": limit}


def _run_process_new_recipes() -> None:
    """Background worker — runs all enrichment steps and logs results."""
    logger.info("process_new_recipes: background task started")
    try:
        import json as _json
        import anthropic as _anthropic
        from app.db.session import SessionLocal
        from app.db.models import RawRecipe
        from app.card_renderer import (
            generate_card_steps, generate_card_title, resolve_card_image, _extract_title,
        )
        from app.classifier import classify_unclassified, classify_unclassified_components

        client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
        db = SessionLocal()
        try:
            # ── 1. Classify ────────────────────────────────────────────────────
            try:
                classified = classify_unclassified(db, client=client, limit=50)
                logger.info("process_new_recipes: classify done — classified=%d", classified)
            except Exception as exc:
                logger.warning("process_new_recipes: classify failed — %s", exc)

            # ── 2. Card steps ──────────────────────────────────────────────────
            try:
                rows = (
                    db.query(RawRecipe)
                    .filter(
                        RawRecipe.card_steps.is_(None),
                        RawRecipe.raw_content.isnot(None),
                        RawRecipe.quick_steps.isnot(None),
                    )
                    .limit(20)
                    .all()
                )
                saved = 0
                for recipe in rows:
                    try:
                        title = _extract_title(recipe.raw_content or "")
                        steps, tip, summary = generate_card_steps(recipe.raw_content, title)
                        if steps:
                            recipe.card_steps = _json.dumps(steps)
                            recipe.card_tip = tip
                            recipe.card_summary = summary
                            saved += 1
                    except Exception as exc:
                        logger.warning("process_new_recipes: card_steps recipe %s — %s", recipe.id, exc)
                if saved:
                    db.commit()
                logger.info("process_new_recipes: card_steps done — saved=%d attempted=%d", saved, len(rows))
            except Exception as exc:
                logger.warning("process_new_recipes: card_steps step failed — %s", exc)

            # ── 3. Card titles ─────────────────────────────────────────────────
            try:
                rows = (
                    db.query(RawRecipe)
                    .filter(
                        RawRecipe.card_title.is_(None),
                        RawRecipe.quick_steps.isnot(None),
                    )
                    .limit(50)
                    .all()
                )
                saved = 0
                for recipe in rows:
                    try:
                        title = generate_card_title(
                            raw_content=recipe.raw_content or "",
                            card_summary=recipe.card_summary or "",
                            cuisine=recipe.cuisine or "",
                        )
                        if title:
                            recipe.card_title = title
                            saved += 1
                    except Exception as exc:
                        logger.warning("process_new_recipes: card_title recipe %s — %s", recipe.id, exc)
                if saved:
                    db.commit()
                logger.info("process_new_recipes: card_titles done — saved=%d attempted=%d", saved, len(rows))
            except Exception as exc:
                logger.warning("process_new_recipes: card_titles step failed — %s", exc)

            # ── 4. Card images ─────────────────────────────────────────────────
            try:
                import time as _time
                # New recipes (NULL) get priority; also retry a small batch of
                # previously-failed recipes so they self-heal over daily runs.
                new_rows = (
                    db.query(RawRecipe)
                    .filter(RawRecipe.card_image_url.is_(None))
                    .limit(10)
                    .all()
                )
                retry_rows = (
                    db.query(RawRecipe)
                    .filter(RawRecipe.card_image_url == "unavailable")
                    .limit(3)
                    .all()
                )
                rows = new_rows + retry_rows
                saved = 0
                for i, recipe in enumerate(rows):
                    if i > 0:
                        _time.sleep(5)  # avoid Replicate burst rate limit
                    try:
                        ingredients = [
                            {"name": ing.ingredient_name, "qty": ing.quantity or "", "unit": ing.unit or ""}
                            for ing in recipe.ingredients
                        ]
                        title = recipe.card_title or _extract_title(recipe.raw_content or "")
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
                    except Exception as exc:
                        logger.warning("process_new_recipes: card_image recipe %s — %s", recipe.id, exc)
                if rows:
                    db.commit()
                logger.info(
                    "process_new_recipes: card_images done — saved=%d new=%d retried=%d",
                    saved, len(new_rows), len(retry_rows),
                )
            except Exception as exc:
                logger.warning("process_new_recipes: card_images step failed — %s", exc)

            # ── 5. Components ──────────────────────────────────────────────────
            try:
                saved = classify_unclassified_components(db, client=client, limit=20)
                logger.info("process_new_recipes: components done — saved=%d", saved)
            except Exception as exc:
                logger.warning("process_new_recipes: components step failed — %s", exc)

            logger.info("process_new_recipes: background task complete")
        finally:
            db.close()
    except Exception as exc:
        logger.error("process_new_recipes: background task crashed — %s", exc, exc_info=True)


@router.post("/process-new-recipes", status_code=202)
def process_new_recipes(
    background_tasks: "BackgroundTasks",
    _: None = Depends(_require_cron_secret),
):
    """
    Kick off the end-to-end enrichment pipeline for newly ingested recipes.

    Returns 202 immediately — all work runs in the background so the caller
    (cron-job.org, Railway cron) does not time out. Progress is visible in
    Railway logs.

    Steps run in order:
      1. classify    (≤50)  — difficulty, cuisine, meal_type, quick_steps
      2. card_steps  (≤20)  — 5-6 detailed steps, tip, summary via Claude Haiku
      3. card_titles (≤50)  — clean dish name via Claude Haiku
      4. card_images (≤10)  — YouTube thumbnail or Flux fallback
      5. components  (≤20)  — base/flavor/protein component labels
    """
    background_tasks.add_task(_run_process_new_recipes)
    return {"status": "accepted", "message": "Pipeline started in background — check Railway logs for progress"}


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


@router.post("/generate-card-image")
def generate_card_image(
    recipe_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Force-generate a Flux image for a specific recipe, skipping the YouTube thumbnail.

    Use this when a thumbnail exists but looks bad (triptych, bad crop, wrong content).
    Overwrites whatever is currently stored in card_image_url.
    """
    from app.db.models import RawRecipe
    from app.card_renderer import _build_flux_prompt, _generate_with_flux, _extract_title
    from app.storage import upload_image

    recipe = db.query(RawRecipe).filter(RawRecipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(404, f"Recipe {recipe_id} not found")

    if not settings.replicate_api_key:
        raise HTTPException(500, "REPLICATE_API_KEY not configured")

    ingredients = [
        {"name": i.ingredient_name, "qty": i.quantity or "", "unit": i.unit or ""}
        for i in recipe.ingredients
    ]
    title = _extract_title(recipe.raw_content or "") or recipe.cuisine or "Recipe"
    prompt = _build_flux_prompt(title, recipe.cuisine or "", ingredients)

    image_bytes = _generate_with_flux(prompt, settings.replicate_api_key)
    if not image_bytes:
        raise HTTPException(502, "Flux generation failed — check Replicate dashboard")

    filename = f"cards/{recipe_id}.webp"
    url = upload_image(image_bytes, filename=filename, content_type="image/webp")
    if not url:
        raise HTTPException(502, "Supabase upload failed")

    recipe.card_image_url = url
    db.commit()
    return {"recipe_id": recipe_id, "card_image_url": url}


@router.post("/scan-image-quality")
def scan_image_quality(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 20,
):
    """
    Review stored card images with Claude vision and reset unsuitable ones for Flux regeneration.

    Flags images that have: human faces, prominent hands, text overlays, triptych/collage
    layouts, portrait orientation, or don't clearly show food.
    Resets card_image_url to NULL — then run resolve-card-images-backlog to replace with Flux.

    Call repeatedly until {"reset": 0}. Each call of 20 images costs ~$0.002 in Claude API.
    """
    import base64
    import httpx as _httpx
    import anthropic as _anthropic
    from app.db.models import RawRecipe

    if not settings.anthropic_api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not configured")

    rows = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_image_url.isnot(None),
            RawRecipe.card_image_url != "unavailable",
        )
        .limit(limit)
        .all()
    )

    client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    checked = 0
    reset = 0

    for recipe in rows:
        try:
            img_resp = _httpx.get(recipe.card_image_url, timeout=15, follow_redirects=True)
            if img_resp.status_code != 200:
                continue
            content_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
            if content_type not in ("image/jpeg", "image/webp", "image/png"):
                continue

            b64 = base64.standard_b64encode(img_resp.content).decode()
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": content_type, "data": b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Is this image suitable for a premium recipe card? "
                                "It must: show food clearly as the main subject, have no human faces, "
                                "no prominent hands or fingers, no text overlays, no triptych/collage "
                                "layout, and be landscape orientation. Reply only YES or NO."
                            ),
                        },
                    ],
                }],
            )
            suitable = "YES" in resp.content[0].text.upper()
            checked += 1
            if not suitable:
                recipe.card_image_url = None
                reset += 1
                logger.info("scan_image_quality: reset recipe %s (failed quality check)", recipe.id)

        except Exception as exc:
            logger.warning("scan_image_quality: recipe %s failed — %s", recipe.id, exc)

    if reset:
        db.commit()

    return {"checked": checked, "reset": reset, "limit": limit}




@router.post("/scan-face-images")
def scan_face_images(
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
    limit: int = 20,
):
    """
    Scan existing stored card images for human faces and reset them for regeneration.

    Checks YouTube-sourced recipes only (faces come from YouTube thumbnails).
    Resets card_image_url to NULL for any image containing a face — then call
    resolve-card-images-backlog to regenerate those with Flux.

    Call repeatedly until {"reset": 0} to clear all face images.
    """
    import httpx as _httpx
    from app.db.models import RawRecipe
    from app.card_renderer import _has_person_face, _youtube_video_id, _is_portrait_thumbnail

    rows = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_image_url.isnot(None),
            RawRecipe.card_image_url != "unavailable",
            RawRecipe.url.ilike("%youtube%"),
        )
        .limit(limit)
        .all()
    )

    checked = 0
    reset = 0
    for recipe in rows:
        try:
            img_resp = _httpx.get(recipe.card_image_url, timeout=15, follow_redirects=True)
            if img_resp.status_code != 200:
                continue
            content_type = img_resp.headers.get("content-type", "image/jpeg").split(";")[0]
            checked += 1
            reject = False
            if "jpeg" in content_type or "jpg" in content_type:
                if _is_portrait_thumbnail(img_resp.content):
                    reject = True
                    logger.info("scan_face_images: reset recipe %s (portrait)", recipe.id)
            if not reject and _has_person_face(img_resp.content, content_type):
                reject = True
                logger.info("scan_face_images: reset recipe %s (face detected)", recipe.id)
            if reject:
                recipe.card_image_url = None
                reset += 1
        except Exception as exc:
            logger.warning("scan_face_images: recipe %s failed — %s", recipe.id, exc)

    if reset:
        db.commit()

    return {"checked": checked, "reset": reset, "limit": limit}


@router.get("/diagnose-image-pipeline")
def diagnose_image_pipeline(
    recipe_id: int | None = None,
    _: None = Depends(_require_cron_secret),
    db: Session = Depends(get_db),
):
    """
    Test each step of the image resolution pipeline and report what's working.

    Steps checked:
      1. Replicate API key present
      2. Supabase configured
      3. Flux generation (one test image)
      4. Supabase upload
      5. Face check via Claude vision (if recipe_id given and it's YouTube)

    Use this to diagnose why resolve-card-images-backlog is saving 0.
    """
    import httpx
    from app.db.models import RawRecipe
    from app.card_renderer import _generate_with_flux, _fetch_thumbnail, _youtube_video_id, _has_person_face
    from app.storage import upload_image

    result: dict = {}

    # 1. Config check
    result["replicate_key_set"] = bool(settings.replicate_api_key)
    result["supabase_configured"] = bool(settings.supabase_url and settings.supabase_service_key)
    result["anthropic_key_set"] = bool(settings.anthropic_api_key)

    # 2. Optional: check YouTube thumbnail + face gate for a specific recipe
    if recipe_id:
        recipe = db.query(RawRecipe).filter(RawRecipe.id == recipe_id).first()
        if recipe:
            video_id = _youtube_video_id(recipe.url)
            result["recipe_url"] = recipe.url
            result["youtube_video_id"] = video_id
            result["card_image_url"] = recipe.card_image_url
            if video_id:
                try:
                    thumb = _fetch_thumbnail(video_id)
                    result["thumbnail_fetched"] = thumb is not None
                    if thumb:
                        has_face = _has_person_face(thumb, "image/jpeg")
                        result["thumbnail_has_face"] = has_face
                except Exception as exc:
                    result["thumbnail_error"] = str(exc)

    # 3. Test Flux generation with direct API call to capture full error
    if settings.replicate_api_key:
        try:
            import httpx as _httpx
            test_resp = _httpx.post(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
                headers={
                    "Authorization": f"Bearer {settings.replicate_api_key}",
                    "Content-Type": "application/json",
                    "Prefer": "wait",
                },
                json={"input": {"prompt": "bowl of tomato soup", "num_outputs": 1, "num_inference_steps": 4}},
                timeout=90,
            )
            result["replicate_http_status"] = test_resp.status_code
            body = test_resp.json()
            if test_resp.status_code != 201:
                result["flux_generation"] = f"error {test_resp.status_code}"
                result["replicate_error"] = body.get("detail") or body.get("error") or str(body)
            else:
                output = body.get("output") or []
                result["flux_generation"] = "ok" if output else f"no output — status={body.get('status')} error={body.get('error')}"
                result["flux_bytes"] = 0

                if output:
                    img = _httpx.get(str(output[0]), timeout=30)
                    result["flux_bytes"] = len(img.content)

                    # 4. Test Supabase upload
                    if settings.supabase_url and settings.supabase_service_key:
                        try:
                            url = upload_image(img.content, filename="diagnostics/test.webp", content_type="image/webp")
                            result["supabase_upload"] = "ok" if url else "returned None"
                            result["supabase_test_url"] = url
                        except Exception as exc:
                            result["supabase_upload"] = f"error: {exc}"
        except Exception as exc:
            result["flux_generation"] = f"exception: {exc}"
    else:
        result["flux_generation"] = "skipped — REPLICATE_API_KEY not set"

    return result



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


@router.get("/preview-theme-cover")
def preview_theme_cover(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Render the cover page for a theme pack as a PDF and return it for download.

    Use this to review the cover design before generating the full 4-page pack.

    Query params:
        slug    Theme slug, e.g. asian-kitchen, quick-cook
    """
    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader
    from app.themes import THEME_BY_SLUG
    from app.theme_selector import select_recipes_for_theme
    from app.db.models import RawRecipe
    from app.pdf_renderer import _render_with_playwright

    theme = THEME_BY_SLUG.get(slug)
    if not theme:
        raise HTTPException(404, f"Theme '{slug}' not found. Available: {list(THEME_BY_SLUG.keys())}")
    if not theme.active:
        raise HTTPException(400, f"Theme '{slug}' is not yet active.")

    ids = select_recipes_for_theme(theme, db)
    recipes_db = db.query(RawRecipe).filter(RawRecipe.id.in_(ids)).all()
    by_id = {r.id: r for r in recipes_db}

    recipes = [
        {
            "title":     by_id[i].card_title or "",
            "cuisine":   by_id[i].cuisine or "",
            "image_url": by_id[i].card_image_url,
            "prep_time": by_id[i].prep_time,
        }
        for i in ids if i in by_id
    ]

    template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    html = env.get_template("theme_cover.html").render(theme=theme, recipes=recipes)

    pdf_bytes = _render_with_playwright(html, week_label="Theme Cover")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cover-{slug}.pdf"},
    )


@router.post("/generate-theme-packs")
def generate_theme_packs(
    slug: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Pre-generate theme pack PDFs and upload them to Supabase Storage.

    Iterates all active themes (or a single theme if slug is given), generates
    the 4-page PDF (cover + 3 recipe cards), uploads to Supabase under
    theme-packs/{slug}.pdf, and returns a summary of results.

    Query params:
        slug    (optional) Only generate one theme, e.g. asian-kitchen
    """
    from app.themes import ACTIVE_THEMES, THEME_BY_SLUG
    from app.theme_pack_generator import generate_theme_pack_pdf
    from app.storage import upload_theme_pdf

    if slug:
        theme = THEME_BY_SLUG.get(slug)
        if not theme:
            raise HTTPException(404, f"Theme '{slug}' not found. Available: {list(THEME_BY_SLUG.keys())}")
        if not theme.active:
            raise HTTPException(400, f"Theme '{slug}' is not active (placeholder).")
        themes_to_generate = [theme]
    else:
        themes_to_generate = ACTIVE_THEMES

    results = {}
    for theme in themes_to_generate:
        logger.info("generate_theme_packs: starting '%s'", theme.slug)
        try:
            pdf_bytes = generate_theme_pack_pdf(theme, db)
            url = upload_theme_pdf(pdf_bytes, slug=theme.slug)
            results[theme.slug] = {
                "status": "ok",
                "pdf_bytes": len(pdf_bytes),
                "storage_url": url,
            }
            logger.info("generate_theme_packs: '%s' done — %d bytes → %s", theme.slug, len(pdf_bytes), url)
        except Exception as exc:
            logger.error("generate_theme_packs: '%s' failed — %s", theme.slug, exc, exc_info=True)
            results[theme.slug] = {"status": "error", "detail": str(exc)}

    return {"generated": len([v for v in results.values() if v["status"] == "ok"]), "results": results}


@router.get("/preview-theme-pack")
def preview_theme_pack(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Generate and download the full 4-page theme pack PDF (cover + 3 recipe cards).

    Use this to review the complete pack before publishing. Each call runs
    Claude recipe selection and Playwright rendering, so it takes ~10 seconds.

    Query params:
        slug    Theme slug, e.g. asian-kitchen, quick-cook
    """
    from app.themes import THEME_BY_SLUG
    from app.theme_pack_generator import generate_theme_pack_pdf

    theme = THEME_BY_SLUG.get(slug)
    if not theme:
        raise HTTPException(404, f"Theme '{slug}' not found. Available: {list(THEME_BY_SLUG.keys())}")
    if not theme.active:
        raise HTTPException(400, f"Theme '{slug}' is not active (placeholder).")

    pdf_bytes = generate_theme_pack_pdf(theme, db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=theme-pack-{slug}.pdf"},
    )


@router.get("/preview-theme-selection")
def preview_theme_selection(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Preview which 3 recipes Claude would pick for a given theme.

    Use this to sanity-check recipe selection before generating the full PDF.
    Returns the selected recipe IDs, titles, and Claude's reasoning.

    Query params:
        slug    Theme slug, e.g. asian-kitchen, quick-cook, comfort-food
    """
    from app.themes import THEME_BY_SLUG
    from app.theme_selector import select_recipes_for_theme
    from app.db.models import RawRecipe

    theme = THEME_BY_SLUG.get(slug)
    if not theme:
        raise HTTPException(404, f"Theme '{slug}' not found. Available: {list(THEME_BY_SLUG.keys())}")
    if not theme.active:
        raise HTTPException(400, f"Theme '{slug}' is not yet active (placeholder).")

    ids = select_recipes_for_theme(theme, db)

    recipes = db.query(RawRecipe).filter(RawRecipe.id.in_(ids)).all()
    by_id = {r.id: r for r in recipes}

    return {
        "theme": slug,
        "selected": [
            {
                "id": i,
                "card_title": by_id[i].card_title if i in by_id else None,
                "cuisine": by_id[i].cuisine if i in by_id else None,
                "card_summary": (by_id[i].card_summary or "")[:150] if i in by_id else None,
            }
            for i in ids
        ],
    }


@router.post("/reset-card-image")
def reset_card_image(
    recipe_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_cron_secret),
):
    """
    Mark a recipe's card image for regeneration by clearing card_image_url.

    After calling this, run resolve-card-images-backlog (with retry_unavailable=false)
    to pick up a fresh Flux-generated image for the recipe.

    Use this when a thumbnail contains a person's face or is otherwise unsuitable.
    """
    from app.db.models import RawRecipe
    recipe = db.query(RawRecipe).filter(RawRecipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(404, f"Recipe {recipe_id} not found")
    old_url = recipe.card_image_url
    recipe.card_image_url = None
    db.commit()
    return {"recipe_id": recipe_id, "status": "reset", "old_url": old_url}


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
    from app.card_renderer import _macro_pct, DIFFICULTY_COLORS, DIETARY_ABBR, _extract_title, ingredient_to_dict
    from app.pdf_renderer import _render_with_playwright

    # Prefer fully-populated recipes; fall back to any classified recipe with steps
    base = db.query(RawRecipe).filter(RawRecipe.card_steps.isnot(None))
    full = base.filter(
        RawRecipe.card_image_url.isnot(None),
        RawRecipe.card_image_url != "unavailable",
    )
    if recipe_id:
        recipe = full.filter(RawRecipe.id == recipe_id).first() \
                 or base.filter(RawRecipe.id == recipe_id).first()
    else:
        recipe = full.first() or base.first()

    if not recipe:
        raise HTTPException(404, "No classified recipe with card_steps found. Run generate-card-steps-backlog first.")

    # Resolve image inline if missing or previously failed
    if not recipe.card_image_url or recipe.card_image_url == "unavailable":
        from app.card_renderer import resolve_card_image, _extract_title as _et
        from app.db.models import Ingredient as _Ing
        _ings = db.query(_Ing).filter(_Ing.recipe_id == recipe.id).all()
        _title = recipe.card_title or _et(recipe.raw_content or "")
        logger.info("preview_card: resolving missing image for recipe %s", recipe.id)
        url = resolve_card_image(
            recipe_id=recipe.id,
            title=_title,
            cuisine=recipe.cuisine or "",
            ingredients=[{"name": i.ingredient_name, "qty": i.quantity or "", "unit": i.unit or ""} for i in _ings],
            source_url=recipe.url,
        )
        if url:
            recipe.card_image_url = url
            db.commit()
            logger.info("preview_card: image resolved for recipe %s", recipe.id)
        else:
            recipe.card_image_url = "unavailable"
            db.commit()
            logger.warning("preview_card: image resolution failed for recipe %s", recipe.id)

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

    title = (
        recipe.card_title                                          # stored AI title (best)
        or _extract_title(recipe.raw_content or "")               # extracted from raw content
        or (recipe.card_summary or "").split(".")[0].strip()      # first sentence of summary
        or recipe.cuisine                                          # last resort
        or "Recipe"
    )

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
        "ingredients":  [ingredient_to_dict(i) for i in ingredients],
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

"""Inbound webhooks from third-party services."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import GumroadSale
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Gumroad permalink → (internal slug, display name, Supabase path)
# ---------------------------------------------------------------------------
_THEME_PACK_PRODUCTS: dict[str, dict] = {
    "asian_theme":       {"slug": "asian-kitchen",   "name": "Asian Kitchen",   "pdf_path": "theme-packs/asian-kitchen.pdf"},
    "mexican_theme":     {"slug": "mexican-fiesta",  "name": "Mexican Fiesta",  "pdf_path": "theme-packs/mexican-fiesta.pdf"},
    "lightfresh_theme":  {"slug": "light-and-fresh", "name": "Light & Fresh",   "pdf_path": "theme-packs/light-and-fresh.pdf"},
    "quickcook_theme":   {"slug": "quick-cook",      "name": "Quick Cook",      "pdf_path": "theme-packs/quick-cook.pdf"},
    "comfort_theme":     {"slug": "comfort-food",    "name": "Comfort Food",    "pdf_path": "theme-packs/comfort-food.pdf"},
    "mediterranean_theme": {"slug": "mediterranean", "name": "Mediterranean",   "pdf_path": "theme-packs/mediterranean.pdf"},
    "italian_theme":     {"slug": "italian-classics","name": "Italian Classics","pdf_path": "theme-packs/italian-classics.pdf"},
    "middleeastern_theme": {"slug": "middle-eastern","name": "Middle Eastern",  "pdf_path": "theme-packs/middle-eastern.pdf"},
    "highprotein_theme": {"slug": "high-protein",    "name": "High Protein",    "pdf_path": "theme-packs/high-protein.pdf"},
    "onepan_theme":      {"slug": "one-pan",         "name": "One Pan",         "pdf_path": "theme-packs/one-pan.pdf"},
}


def _require_webhook_token(token: str = Query(default="")) -> None:
    """Reject requests that don't carry the correct webhook token."""
    if not settings.gumroad_webhook_token:
        logger.warning("webhooks: GUMROAD_WEBHOOK_TOKEN not set — accepting all requests (unsafe)")
        return
    if token != settings.gumroad_webhook_token:
        raise HTTPException(status_code=403, detail="Invalid webhook token")


def _fetch_pdf_from_supabase(pdf_path: str) -> bytes:
    """Download a PDF from Supabase Storage and return its bytes."""
    bucket = settings.supabase_storage_bucket
    url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{pdf_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


@router.post("/gumroad-sale")
def gumroad_sale(
    _: None = Depends(_require_webhook_token),
    db: Session = Depends(get_db),
    # Gumroad sends form-encoded fields
    sale_id: str = Form(default=""),
    email: str = Form(default=""),
    product_permalink: str = Form(default=""),
    product_name: str = Form(default=""),
    test: str = Form(default="false"),
    refunded: str = Form(default="false"),
) -> dict:
    """
    Receive a Gumroad purchase webhook, fetch the purchased PDF from Supabase,
    and email it to the buyer via Resend.

    Register this URL in Gumroad → Settings → Advanced → Ping:
        https://<your-domain>/webhooks/gumroad-sale?token=<GUMROAD_WEBHOOK_TOKEN>
    """
    from app.email_sender import send_purchase_email

    logger.info(
        "webhooks/gumroad-sale: received sale_id=%s product=%s email=%s test=%s refunded=%s",
        sale_id, product_permalink, email, test, refunded,
    )

    # ── Ignore refunds and test pings ────────────────────────────────────────
    if refunded.lower() == "true":
        logger.info("webhooks/gumroad-sale: ignoring refund for sale_id=%s", sale_id)
        return {"status": "ignored", "reason": "refund"}

    if test.lower() == "true":
        logger.info("webhooks/gumroad-sale: test ping received — not delivering")
        return {"status": "ok", "reason": "test"}

    # ── Validate required fields ─────────────────────────────────────────────
    if not sale_id or not email or not product_permalink:
        logger.error("webhooks/gumroad-sale: missing required fields")
        raise HTTPException(status_code=400, detail="Missing required fields")

    # ── Prevent duplicate delivery ───────────────────────────────────────────
    existing = db.query(GumroadSale).filter(GumroadSale.order_id == sale_id).first()
    if existing:
        logger.info("webhooks/gumroad-sale: sale_id=%s already processed — skipping", sale_id)
        return {"status": "ok", "reason": "already_processed"}

    # ── Look up product ──────────────────────────────────────────────────────
    product = _THEME_PACK_PRODUCTS.get(product_permalink)
    if not product:
        logger.warning(
            "webhooks/gumroad-sale: unknown permalink %r — no delivery (sale_id=%s)",
            product_permalink, sale_id,
        )
        # Record it so we can investigate, but don't fail the webhook
        sale = GumroadSale(
            order_id=sale_id,
            email=email,
            product_permalink=product_permalink,
            pdf_path="",
            delivered=False,
        )
        db.add(sale)
        db.commit()
        return {"status": "ok", "reason": "unknown_product"}

    # ── Record the sale before delivery (so a crash mid-send doesn't re-deliver) ──
    sale = GumroadSale(
        order_id=sale_id,
        email=email,
        product_permalink=product_permalink,
        pdf_path=product["pdf_path"],
        delivered=False,
    )
    db.add(sale)
    db.commit()

    # ── Fetch PDF from Supabase ──────────────────────────────────────────────
    try:
        pdf_bytes = _fetch_pdf_from_supabase(product["pdf_path"])
    except Exception as exc:
        logger.error(
            "webhooks/gumroad-sale: failed to fetch PDF %s for sale_id=%s — %s",
            product["pdf_path"], sale_id, exc,
        )
        # Don't raise — Gumroad will retry on 5xx; return 200 to avoid spam retries
        return {"status": "error", "reason": "pdf_fetch_failed"}

    # ── Send delivery email ──────────────────────────────────────────────────
    pdf_filename = f"mealengine-{product['slug']}.pdf"
    delivered = send_purchase_email(
        to_email=email,
        product_name=product["name"],
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )

    # ── Mark as delivered ────────────────────────────────────────────────────
    sale.delivered = delivered
    sale.created_at = datetime.now(timezone.utc)
    db.commit()

    if delivered:
        logger.info(
            "webhooks/gumroad-sale: delivered %s to %s (sale_id=%s)",
            product["name"], email, sale_id,
        )
    else:
        logger.error(
            "webhooks/gumroad-sale: email delivery failed for %s sale_id=%s",
            email, sale_id,
        )

    return {"status": "ok", "delivered": delivered}

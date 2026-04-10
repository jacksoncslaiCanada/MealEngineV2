"""Gumroad API integration.

Updates the product's custom_delivery_url on a standing Gumroad listing
so buyers always download the current week's plan from Supabase Storage.
This avoids the unreliable product_files upload endpoint entirely.
"""
from __future__ import annotations

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.gumroad.com/v2"


def _product_id_for_variant(variant: str) -> str | None:
    mapping = {
        "little_ones": settings.gumroad_product_little_ones,
        "teen_table":  settings.gumroad_product_teen_table,
    }
    return mapping.get(variant) or None


def update_product_url(*, variant: str, storage_url: str) -> bool:
    """Point the Gumroad product's delivery URL to the current week's Supabase PDF.

    Uses PUT /v2/products/:id with custom_delivery_url instead of file upload.
    Returns True on success.
    """
    if not settings.gumroad_access_token:
        logger.warning("gumroad: GUMROAD_ACCESS_TOKEN not set — skipping update")
        return False

    product_id = _product_id_for_variant(variant)
    if not product_id:
        logger.warning("gumroad: no product ID configured for variant '%s'", variant)
        return False

    try:
        resp = httpx.put(
            f"{_BASE}/products/{product_id}",
            params={"access_token": settings.gumroad_access_token},
            data={"custom_delivery_url": storage_url},
            timeout=30,
        )
        logger.info("gumroad: response %s — %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
        logger.info("gumroad: updated delivery URL for %s → %s", variant, storage_url)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("gumroad: API error %s — %s", exc.response.status_code, exc.response.text[:500])
        return False
    except Exception as exc:
        logger.error("gumroad: unexpected error — %s", exc)
        return False


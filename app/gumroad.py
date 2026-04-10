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


def _get_internal_id(permalink: str) -> str | None:
    """Fetch the internal base64 product ID from Gumroad using the permalink slug.

    Gumroad's GET endpoint accepts the permalink slug, but PUT requires
    the internal ID (e.g. 'RAsVx1hwFfsA6fHKmn7XfA==').
    """
    try:
        resp = httpx.get(
            f"{_BASE}/products/{permalink}",
            params={"access_token": settings.gumroad_access_token},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["product"]["id"]
    except Exception as exc:
        logger.error("gumroad: failed to fetch internal ID for '%s' — %s", permalink, exc)
        return None


def update_product_url(*, variant: str, storage_url: str) -> bool:
    """Point the Gumroad product's delivery URL to the current week's Supabase PDF.

    Uses PUT /v2/products/:internal_id with custom_delivery_url.
    Fetches the internal ID first since PUT requires it, not the permalink slug.
    Returns True on success.
    """
    if not settings.gumroad_access_token:
        logger.warning("gumroad: GUMROAD_ACCESS_TOKEN not set — skipping update")
        return False

    permalink = _product_id_for_variant(variant)
    if not permalink:
        logger.warning("gumroad: no product ID configured for variant '%s'", variant)
        return False

    internal_id = _get_internal_id(permalink)
    if not internal_id:
        return False

    try:
        resp = httpx.put(
            f"{_BASE}/products/{internal_id}",
            params={"access_token": settings.gumroad_access_token},
            data={"custom_delivery_url": storage_url},
            timeout=30,
        )
        logger.info("gumroad: PUT response %s — %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
        logger.info("gumroad: updated delivery URL for %s → %s", variant, storage_url)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("gumroad: API error %s — %s", exc.response.status_code, exc.response.text[:500])
        return False
    except Exception as exc:
        logger.error("gumroad: unexpected error — %s", exc)
        return False


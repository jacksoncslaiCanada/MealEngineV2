"""Gumroad API integration.

Updates the product's custom_delivery_url on a standing Gumroad listing
so buyers always download the current week's plan from Supabase Storage.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

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
    """Fetch the internal base64 product ID using the permalink slug."""
    try:
        resp = httpx.get(
            f"{_BASE}/products/{permalink}",
            params={"access_token": settings.gumroad_access_token},
            timeout=10,
        )
        resp.raise_for_status()
        internal_id = resp.json()["product"]["id"]
        logger.info("gumroad: resolved '%s' → internal id '%s'", permalink, internal_id)
        return internal_id
    except Exception as exc:
        logger.error("gumroad: failed to fetch internal ID for '%s' — %s", permalink, exc)
        return None


def update_product_url(*, variant: str, storage_url: str) -> bool:
    """Point the Gumroad product's delivery URL to the current week's Supabase PDF."""
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

    # URL-encode the base64 ID — it contains '=' chars that break URL path parsing
    encoded_id = quote(internal_id, safe="")
    put_url = f"{_BASE}/products/{encoded_id}"
    logger.info("gumroad: PUT %s", put_url)

    try:
        resp = httpx.put(
            put_url,
            params={"access_token": settings.gumroad_access_token},
            data={"custom_delivery_url": storage_url},
            timeout=30,
        )
        logger.info("gumroad: PUT response %s — %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
        logger.info("gumroad: updated delivery URL for %s → %s", variant, storage_url)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("gumroad: API error %s — %s", exc.response.status_code, exc.response.text[:300])
        return False
    except Exception as exc:
        logger.error("gumroad: unexpected error — %s", exc)
        return False


"""Gumroad API integration.

Updates the product file on a standing Gumroad listing so buyers
always see the current week's plan when they visit the product page.
"""
from __future__ import annotations

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.gumroad.com/v2"

# Map variant → Gumroad product ID (configured in Railway env vars)
def _product_id_for_variant(variant: str) -> str | None:
    mapping = {
        "little_ones": settings.gumroad_product_little_ones,
        "teen_table":  settings.gumroad_product_teen_table,
    }
    return mapping.get(variant) or None


def update_product_file(pdf_bytes: bytes, *, variant: str, week_label: str) -> bool:
    """Replace the product file on the Gumroad listing for this variant.

    Gumroad's API requires multipart form upload. Returns True on success.
    """
    if not settings.gumroad_access_token:
        logger.warning("gumroad: GUMROAD_ACCESS_TOKEN not set — skipping update")
        return False

    product_id = _product_id_for_variant(variant)
    if not product_id:
        logger.warning("gumroad: no product ID configured for variant '%s'", variant)
        return False

    filename = f"meal-plan-{week_label}-{variant}.pdf"

    try:
        resp = httpx.post(
            f"{_BASE}/products/{product_id}/product_files",
            headers={"Authorization": f"Bearer {settings.gumroad_access_token}"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            timeout=60,
        )
        resp.raise_for_status()
        logger.info("gumroad: updated product file for %s (%s)", variant, week_label)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("gumroad: API error %s — %s", exc.response.status_code, exc.response.text)
        return False
    except Exception as exc:
        logger.error("gumroad: unexpected error — %s", exc)
        return False

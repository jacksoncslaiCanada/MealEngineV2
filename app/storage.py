"""Supabase Storage upload for generated PDFs.

Uploads weekly plan PDFs to a public Supabase Storage bucket and
returns the public URL. Falls back gracefully if not configured.
"""
from __future__ import annotations

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def upload_pdf(pdf_bytes: bytes, *, variant: str, week_label: str) -> str | None:
    """Upload a PDF to Supabase Storage. Returns the public URL or None on failure."""
    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning("storage: Supabase not configured — skipping upload")
        return None

    filename = f"{week_label}-{variant}.pdf"
    bucket = settings.supabase_storage_bucket
    upload_url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{filename}"

    try:
        resp = httpx.put(
            upload_url,
            content=pdf_bytes,
            headers={
                "Authorization": f"Bearer {settings.supabase_service_key}",
                "Content-Type": "application/pdf",
                "x-upsert": "true",   # overwrite if file exists for this week
            },
            timeout=30,
        )
        resp.raise_for_status()
        public_url = f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{filename}"
        logger.info("storage: uploaded %s → %s", filename, public_url)
        return public_url
    except httpx.HTTPStatusError as exc:
        logger.error("storage: Supabase upload error %s — %s", exc.response.status_code, exc.response.text)
        return None
    except Exception as exc:
        logger.error("storage: unexpected upload error — %s", exc)
        return None

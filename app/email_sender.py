"""Email delivery via Resend API.

Sends the weekly meal plan PDF to a subscriber as an attachment.
Falls back gracefully if Resend is not configured.
"""
from __future__ import annotations

import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def send_plan_email(
    *,
    to_email: str,
    variant_label: str,
    week_label: str,
    pdf_bytes: bytes,
    plans_remaining: int,
) -> bool:
    """Send the weekly plan PDF to one subscriber. Returns True on success."""
    if not settings.resend_api_key:
        logger.warning("email_sender: RESEND_API_KEY not set — skipping email to %s", to_email)
        return False

    filename = f"meal-plan-{week_label}-{variant_label.lower().replace(' ', '-')}.pdf"

    subject = f"Your {variant_label} Meal Plan — {week_label}"

    if plans_remaining <= 1:
        footer = (
            "<p style='color:#6b7280;font-size:12px;margin-top:24px;'>"
            "This is your last plan in your current pack. "
            "<a href='https://mealengine.ca/subscribe'>Subscribe</a> "
            "to keep your weekly plans arriving automatically."
            "</p>"
        )
    else:
        footer = (
            f"<p style='color:#6b7280;font-size:12px;margin-top:24px;'>"
            f"You have {plans_remaining - 1} plan(s) remaining after this one. "
            f"<a href='https://mealengine.ca/subscribe'>Subscribe</a> "
            f"to never run out."
            f"</p>"
        )

    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;color:#1f2937;">
      <h2 style="margin-bottom:4px;">Your weekly meal plan is ready</h2>
      <p style="color:#6b7280;margin-top:0;">{variant_label} · {week_label}</p>
      <p>
        This week's plan is attached as a PDF. Open it to see your
        7-day schedule, 3-step cooking guides, and categorised shopping list.
      </p>
      <p style="margin-top:16px;">
        <strong>Tip:</strong> Print the shopping list or screenshot it before
        you head to the store on the weekend.
      </p>
      {footer}
      <p style="color:#9ca3af;font-size:11px;margin-top:32px;border-top:1px solid #f3f4f6;padding-top:12px;">
        MealEngine · mealengine.ca<br>
        You're receiving this because you purchased a meal plan pack.
      </p>
    </div>
    """

    import base64
    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    payload = {
        "from": f"MealEngine <{settings.email_from}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "attachments": [
            {
                "filename": filename,
                "content": pdf_b64,
            }
        ],
    }

    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("email_sender: sent plan to %s (remaining after=%d)", to_email, plans_remaining - 1)
        return True
    except httpx.HTTPStatusError as exc:
        logger.error("email_sender: Resend API error %s — %s", exc.response.status_code, exc.response.text)
        return False
    except Exception as exc:
        logger.error("email_sender: unexpected error sending to %s — %s", to_email, exc)
        return False


def send_conversion_email(*, to_email: str, variant_label: str) -> bool:
    """Send a conversion nudge when a subscriber has used all their plans."""
    if not settings.resend_api_key:
        return False

    html_body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;color:#1f2937;">
      <h2>Your meal plan pack has ended</h2>
      <p>
        You've used all 4 weeks of your {variant_label} pack.
        We hope meal planning made your week a little easier.
      </p>
      <p>
        To keep your weekly plan arriving automatically every Saturday morning,
        subscribe for <strong>$12/month</strong> — cancel any time.
      </p>
      <p style="margin-top:24px;">
        <a href="https://mealengine.ca/subscribe"
           style="background:#1f2937;color:#fff;padding:10px 20px;
                  border-radius:4px;text-decoration:none;font-weight:600;">
          Keep my weekly plan going
        </a>
      </p>
      <p style="color:#9ca3af;font-size:11px;margin-top:32px;border-top:1px solid #f3f4f6;padding-top:12px;">
        MealEngine · mealengine.ca
      </p>
    </div>
    """

    payload = {
        "from": f"MealEngine <{settings.email_from}>",
        "to": [to_email],
        "subject": f"Your {variant_label} pack is complete — keep it going?",
        "html": html_body,
    }

    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("email_sender: sent conversion email to %s", to_email)
        return True
    except Exception as exc:
        logger.error("email_sender: conversion email failed for %s — %s", to_email, exc)
        return False

"""Contextual recipe selection for theme packs.

Uses Claude to read candidate recipe summaries and pick the 3 that best
match a theme's intent — more semantic than tag-based filtering.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.themes import ThemePack

logger = logging.getLogger(__name__)

_MIN_CUISINE_POOL = 15  # minimum matches before using cuisine pre-filter


def select_recipes_for_theme(
    theme: "ThemePack",
    db: "Session",
    max_candidates: int = 100,
) -> list[int]:
    """Return exactly 3 recipe IDs that best match the theme.

    1. If the theme has cuisine_keywords, try a focused DB query first.
       Uses the full pool only if that returns fewer than _MIN_CUISINE_POOL results.
    2. Sends compact summaries to Claude Haiku with a strict prompt.
    3. Falls back to top engagement-score recipes if Claude fails.
    """
    import anthropic
    from app.config import settings
    from app.db.models import RawRecipe
    from sqlalchemy import or_, func

    base_filter = [
        RawRecipe.card_title.isnot(None),
        RawRecipe.card_steps.isnot(None),
        RawRecipe.card_image_url.isnot(None),
        RawRecipe.card_image_url != "unavailable",
        # Exclude classified sides and desserts; NULL = unclassified, still eligible
        or_(RawRecipe.course == "main", RawRecipe.course.is_(None)),
        # Exclude pure components (base, protein, sauce, veggie) — theme packs
        # want complete dishes. NULL = unclassified, still eligible.
        or_(
            RawRecipe.blueprint_role == "complete",
            RawRecipe.blueprint_role.is_(None),
        ),
    ]

    candidates = []

    # ── Cuisine-focused pre-filter ─────────────────────────────────────────────
    if theme.cuisine_keywords:
        cuisine_clauses = [
            func.lower(RawRecipe.cuisine).contains(kw.lower())
            for kw in theme.cuisine_keywords
        ]
        focused = (
            db.query(RawRecipe)
            .filter(*base_filter, or_(*cuisine_clauses))
            .order_by(RawRecipe.engagement_score.desc().nullslast())
            .limit(max_candidates)
            .all()
        )
        if len(focused) >= _MIN_CUISINE_POOL:
            candidates = focused
            logger.info(
                "theme_selector: using focused pool of %d recipes for '%s'",
                len(candidates), theme.slug,
            )

    # ── Fall back to full pool ─────────────────────────────────────────────────
    if not candidates:
        candidates = (
            db.query(RawRecipe)
            .filter(*base_filter)
            .order_by(RawRecipe.engagement_score.desc().nullslast())
            .limit(max_candidates)
            .all()
        )
        logger.info(
            "theme_selector: using full pool of %d recipes for '%s'",
            len(candidates), theme.slug,
        )

    if len(candidates) < 3:
        raise ValueError(
            f"Not enough enriched recipes to select from (found {len(candidates)}, need 3)"
        )

    id_set = {r.id for r in candidates}

    # ── Build compact candidate list ───────────────────────────────────────────
    lines = []
    for r in candidates:
        summary_excerpt = (r.card_summary or "")[:100].replace("\n", " ")
        cuisine = r.cuisine or "unknown"
        role = r.blueprint_role or "complete"
        lines.append(f"{r.id}: {r.card_title} | {cuisine} | [{role}] | {summary_excerpt}")

    candidate_text = "\n".join(lines)

    prompt = (
        f"You are selecting recipes for a themed meal pack called \"{theme.name}\".\n\n"
        f"THEME: {theme.tagline}\n\n"
        f"SELECTION CRITERIA (read carefully):\n{theme.selection_hint}\n\n"
        f"CANDIDATES (format — id: title | cuisine | [blueprint_role] | summary):\n"
        f"{candidate_text}\n\n"
        f"RULES:\n"
        f"- Choose EXACTLY 3 recipes.\n"
        f"- A recipe MUST clearly match the theme to be selected. Do NOT pick a recipe "
        f"just because it sounds good — theme fit is the only criterion.\n"
        f"- Prefer recipes with blueprint_role 'complete' — they are full standalone dishes.\n"
        f"- If a recipe does not match the theme, skip it entirely.\n"
        f"- Aim for variety: different proteins, cooking styles, or sub-cuisines.\n\n"
        f"Reply ONLY with valid JSON:\n"
        f'{{\"ids\": [id1, id2, id3], \"reasoning\": \"brief note on why each fits\"}}'
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        data = json.loads(text[start:end])
        ids = [int(i) for i in data["ids"]]

        valid = [i for i in ids if i in id_set]
        if len(valid) < 3:
            logger.warning(
                "theme_selector: Claude returned %d valid IDs for '%s', falling back. Response: %s",
                len(valid), theme.slug, text,
            )
            return _fallback_ids(candidates, exclude=valid, total=3)

        logger.info(
            "theme_selector: selected %s for theme '%s' — %s",
            valid[:3], theme.slug, data.get("reasoning", ""),
        )
        return valid[:3]

    except Exception as exc:
        logger.warning("theme_selector: Claude selection failed for '%s' — %s", theme.slug, exc)
        return _fallback_ids(candidates, exclude=[], total=3)


def _fallback_ids(candidates: list, exclude: list[int], total: int) -> list[int]:
    """Return top IDs by engagement score, skipping already-chosen ones."""
    seen = set(exclude)
    result = []
    for r in candidates:
        if r.id not in seen:
            result.append(r.id)
            seen.add(r.id)
        if len(result) == total:
            break
    return result

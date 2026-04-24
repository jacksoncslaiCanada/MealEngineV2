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


def select_recipes_for_theme(
    theme: "ThemePack",
    db: "Session",
    max_candidates: int = 150,
) -> list[int]:
    """Return exactly 3 recipe IDs that best match the theme.

    Queries the DB for fully-enriched recipes, sends compact summaries to
    Claude Haiku, and parses the returned IDs. Falls back to the top 3
    candidates by engagement_score if Claude fails.
    """
    import anthropic
    from app.config import settings
    from app.db.models import RawRecipe

    candidates = (
        db.query(RawRecipe)
        .filter(
            RawRecipe.card_title.isnot(None),
            RawRecipe.card_steps.isnot(None),
            RawRecipe.card_image_url.isnot(None),
            RawRecipe.card_image_url != "unavailable",
        )
        .order_by(RawRecipe.engagement_score.desc().nullslast())
        .limit(max_candidates)
        .all()
    )

    if len(candidates) < 3:
        raise ValueError(f"Not enough enriched recipes to select from (found {len(candidates)}, need 3)")

    # Build compact candidate list for the prompt
    lines = []
    id_set = {r.id for r in candidates}
    for r in candidates:
        summary_excerpt = (r.card_summary or "")[:120].replace("\n", " ")
        cuisine = r.cuisine or "unknown cuisine"
        lines.append(f"{r.id}: {r.card_title} | {cuisine} | {summary_excerpt}")

    candidate_text = "\n".join(lines)

    prompt = (
        f"You are curating a themed recipe pack called \"{theme.name}\".\n\n"
        f"Theme description: {theme.tagline}\n\n"
        f"Selection criteria:\n{theme.selection_hint}\n\n"
        f"Available recipes (format: id: title | cuisine | summary):\n"
        f"{candidate_text}\n\n"
        f"Choose exactly 3 recipes that best match this theme. Aim for variety — "
        f"avoid picking 3 very similar dishes (e.g. 3 chicken stir-fries). "
        f"Prefer recipes where the theme is the primary character of the dish, "
        f"not just a minor influence.\n\n"
        f"Reply ONLY with valid JSON:\n"
        f'{{\"ids\": [id1, id2, id3], \"reasoning\": \"one sentence why each was chosen\"}}'
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        data = json.loads(text[start:end])
        ids = [int(i) for i in data["ids"]]

        # Validate all returned IDs exist in our candidate set
        valid = [i for i in ids if i in id_set]
        if len(valid) < 3:
            logger.warning(
                "theme_selector: Claude returned %d valid IDs for %s, falling back",
                len(valid), theme.slug,
            )
            return _fallback_ids(candidates, exclude=valid)[:3]

        logger.info(
            "theme_selector: selected %s for theme '%s' — %s",
            valid, theme.slug, data.get("reasoning", ""),
        )
        return valid[:3]

    except Exception as exc:
        logger.warning("theme_selector: Claude selection failed for %s — %s", theme.slug, exc)
        return _fallback_ids(candidates, exclude=[])[:3]


def _fallback_ids(candidates: list, exclude: list[int]) -> list[int]:
    """Return top IDs by engagement score, skipping any already chosen."""
    seen = set(exclude)
    result = []
    for r in candidates:
        if r.id not in seen:
            result.append(r.id)
            seen.add(r.id)
        if len(result) == 3:
            break
    return result

"""Recipe card renderer: image resolution, Claude macro estimation + Playwright PDF."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

DIFFICULTY_COLORS = {
    "easy":    "#687f6a",
    "medium":  "#c9943a",
    "complex": "#b5614a",
}

DIETARY_ABBR = {
    "gluten-free": "GF",
    "dairy-free":  "DF",
    "vegetarian":  "V",
    "vegan":       "VG",
    "nut-free":    "NF",
}


# ---------------------------------------------------------------------------
# Image resolution: thumbnail → Flux fallback → Supabase upload
# ---------------------------------------------------------------------------

# YouTube grey placeholder is always < 5 KB; real thumbnails are 20 KB+
_THUMBNAIL_MIN_BYTES = 5_000


def _youtube_video_id(url: str | None) -> str | None:
    """Extract YouTube video ID from a watch or short URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc and parsed.query:
            for part in parsed.query.split("&"):
                if part.startswith("v="):
                    return part[2:]
        if "youtu.be" in parsed.netloc:
            return parsed.path.lstrip("/").split("?")[0] or None
    except Exception:
        pass
    return None


def _jpeg_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    """Return (width, height) from JPEG bytes by scanning SOF markers. Returns None on failure."""
    import struct
    i = 0
    n = len(image_bytes)
    while i < n - 9:
        if image_bytes[i] != 0xFF:
            i += 1
            continue
        marker = image_bytes[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7):
            # SOF: FF Cx [len 2B] [precision 1B] [height 2B] [width 2B]
            h = struct.unpack(">H", image_bytes[i + 5: i + 7])[0]
            w = struct.unpack(">H", image_bytes[i + 7: i + 9])[0]
            return (w, h)
        if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
            i += 2
            continue
        if i + 3 < n:
            seg_len = struct.unpack(">H", image_bytes[i + 2: i + 4])[0]
            i += 2 + seg_len
        else:
            break
    return None


def _is_portrait_thumbnail(image_bytes: bytes) -> bool:
    """Return True if the JPEG is taller than wide (portrait / Shorts-style)."""
    dims = _jpeg_dimensions(image_bytes)
    if dims is None:
        return False
    w, h = dims
    return h > w


def _fetch_thumbnail(video_id: str) -> bytes | None:
    """Try to fetch a real YouTube thumbnail. Returns bytes or None if placeholder/missing."""
    # maxresdefault only exists for videos with custom thumbnails — best quality
    for quality in ("maxresdefault", "hqdefault"):
        url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
        try:
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) >= _THUMBNAIL_MIN_BYTES:
                return resp.content
        except Exception:
            pass
    return None


def _extract_title(raw_content: str) -> str:
    """Best-effort title extraction from raw recipe content."""
    import re
    for line in raw_content.splitlines():
        line = line.strip()
        if not (10 < len(line) < 120):
            continue
        if line.lower().startswith(("http", "#", "/")):
            continue
        # Strip field-label prefixes like "Title:", "Recipe Title:", "Recipe:"
        clean = re.sub(
            r'^(?:title|recipe\s+title|recipe\s+name|recipe|name)\s*[:–\-]\s*',
            '', line, flags=re.IGNORECASE,
        ).strip()
        # Take the first segment before common YouTube title separators
        for sep in (" | ", " – ", " — ", " // ", " - "):
            if sep in clean:
                clean = clean.split(sep)[0].strip()
                break
        # Strip "How to cook/make/bake X" → "X"
        clean = re.sub(
            r'^How\s+to\s+(?:cook|make|prepare|bake|grill|fry|roast|steam|boil)\s+',
            '', clean, flags=re.IGNORECASE,
        ).strip()
        if 5 < len(clean) < 100:
            return clean
    return ""


def _build_flux_prompt(title: str, cuisine: str, ingredients: list[dict]) -> str:
    key_ingredients = ", ".join(i["name"] for i in ingredients[:5])
    cuisine_prefix = f"{cuisine} cuisine, " if cuisine else ""
    return (
        f"Professional food photography of {title}. "
        f"{cuisine_prefix}"
        f"Key ingredients visible: {key_ingredients}. "
        f"Shot from a 45-degree overhead angle on a sage green and warm cream linen backdrop. "
        f"Soft natural window light from the left, minimal white ceramic props, "
        f"fresh herbs as garnish, highly appetising, magazine quality, shallow depth of field."
    )


def _generate_with_flux(prompt: str, api_key: str) -> bytes | None:
    """Generate an image via Flux Schnell on Replicate. Returns raw image bytes or None."""
    try:
        # Use Prefer: wait so Replicate blocks until done (avoids polling in most cases)
        resp = httpx.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            json={
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": "1:1",
                    "output_format": "webp",
                    "output_quality": 85,
                    "num_outputs": 1,
                    "num_inference_steps": 4,
                }
            },
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output") or []

        # If Prefer: wait timed out, poll until done
        if not output and data.get("id"):
            prediction_id = data["id"]
            for _ in range(30):
                time.sleep(2)
                poll = httpx.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                poll_data = poll.json()
                if poll_data.get("status") == "succeeded":
                    output = poll_data.get("output") or []
                    break
                if poll_data.get("status") in ("failed", "canceled"):
                    logger.warning("card_renderer: Flux prediction %s %s", prediction_id, poll_data.get("status"))
                    return None

        if not output:
            return None

        img_resp = httpx.get(str(output[0]), timeout=30)
        img_resp.raise_for_status()
        return img_resp.content

    except Exception as exc:
        logger.warning("card_renderer: Flux generation failed — %s", exc)
        return None


def _has_person_face(image_bytes: bytes, content_type: str = "image/jpeg") -> bool:
    """Return True if the image contains a human face or person using Claude vision."""
    import base64
    import anthropic
    try:
        from app.config import settings
        if not settings.anthropic_api_key:
            return False
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        b64 = base64.standard_b64encode(image_bytes).decode()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64}},
                    {"type": "text", "text": "Does this image contain a human face or person? Reply only YES or NO."},
                ],
            }],
        )
        return "YES" in resp.content[0].text.upper()
    except Exception as exc:
        logger.warning("card_renderer: face check failed — %s", exc)
        return False


def resolve_card_image(
    recipe_id: int,
    title: str,
    cuisine: str,
    ingredients: list[dict],
    source_url: str | None,
) -> str | None:
    """Resolve the best image for a recipe card and store it in Supabase.

    Priority:
      1. YouTube thumbnail (fetched directly if real, not placeholder)
      2. Flux Schnell generation (sage/cream backdrop, consistent style)

    Returns the Supabase public URL, or None if both sources fail / not configured.
    """
    from app.config import settings
    from app.storage import upload_image

    image_bytes: bytes | None = None
    content_type = "image/jpeg"

    # --- Try YouTube thumbnail (reject portraits and faces) ---
    video_id = _youtube_video_id(source_url)
    if video_id:
        thumb = _fetch_thumbnail(video_id)
        if thumb:
            if _is_portrait_thumbnail(thumb):
                logger.info("card_renderer: thumbnail is portrait, falling back to Flux for recipe %s", recipe_id)
            elif _has_person_face(thumb, "image/jpeg"):
                logger.info("card_renderer: thumbnail has person face, falling back to Flux for recipe %s", recipe_id)
            else:
                image_bytes = thumb
                logger.info("card_renderer: using YouTube thumbnail for recipe %s", recipe_id)

    # --- Fall back to Flux ---
    if image_bytes is None:
        if not settings.replicate_api_key:
            logger.info("card_renderer: no Replicate key — skipping Flux generation")
            return None
        prompt = _build_flux_prompt(title, cuisine, ingredients)
        image_bytes = _generate_with_flux(prompt, settings.replicate_api_key)
        content_type = "image/webp"
        if image_bytes:
            logger.info("card_renderer: generated Flux image for recipe %s", recipe_id)

    if not image_bytes:
        return None

    # --- Upload to Supabase recipe-images bucket ---
    ext = "jpg" if content_type == "image/jpeg" else "webp"
    filename = f"cards/{recipe_id}.{ext}"
    return upload_image(image_bytes, filename=filename, content_type=content_type)


def generate_food_image(title: str, cuisine: str, ingredients: list[dict]) -> str | None:
    """Generate a food photo via DALL-E 3. Returns a base64 data URI or None on failure."""
    try:
        from openai import OpenAI
        from app.config import settings
        if not settings.openai_api_key:
            logger.info("card_renderer: no OpenAI key — skipping image generation")
            return None

        key_ingredients = ", ".join(i["name"] for i in ingredients[:5])
        cuisine_prefix = f"{cuisine} cuisine, " if cuisine else ""

        prompt = (
            f"Professional food photography of {title}. "
            f"{cuisine_prefix}"
            f"Key ingredients visible: {key_ingredients}. "
            f"Shot from a 45-degree overhead angle on a sage green and warm cream linen backdrop. "
            f"Soft natural window light from the left, minimal white ceramic props, "
            f"fresh herbs as garnish, highly appetising, magazine quality, shallow depth of field."
        )

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            response_format="b64_json",
            n=1,
        )
        b64 = response.data[0].b64_json
        return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.warning("card_renderer: image generation failed — %s", exc)
        return None


def generate_card_title(raw_content: str, card_summary: str, cuisine: str) -> str:
    """Generate a clean 3-6 word dish name using Claude Haiku. Returns '' on failure."""
    try:
        import anthropic
        from app.config import settings
        if not settings.anthropic_api_key:
            return ""

        context = ""
        if card_summary:
            context += f"Summary: {card_summary[:200]}\n"
        if raw_content:
            context += f"Content excerpt: {raw_content[:500]}"

        prompt = (
            f"Extract or generate a short, clean dish name (3-6 words) from this recipe content.\n"
            f"Cuisine: {cuisine or 'unknown'}\n"
            f"{context}\n\n"
            f"Rules:\n"
            f"- Just the dish name, nothing else\n"
            f"- No 'How to make', 'Easy', 'Best ever', 'Recipe' suffix\n"
            f"- No channel names or author names\n"
            f"- Capitalise each word\n"
            f"Examples: 'Crispy Garlic Butter Chicken', 'No-Bake Peanut Butter Bars', 'Creamy Mushroom Pasta'\n\n"
            f"Dish name:"
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}],
        )
        title = resp.content[0].text.strip().strip('"').strip("'")
        return title if 3 < len(title) < 80 else ""
    except Exception as exc:
        logger.warning("card_renderer: title generation failed — %s", exc)
        return ""


def estimate_macros(title: str, ingredients: list[dict], servings: int) -> dict:
    """Estimate per-serving macros via Claude Haiku. Returns {cals, protein, carbs, fat}."""
    default: dict = {"cals": 0, "protein": 0, "carbs": 0, "fat": 0}
    try:
        import anthropic
        from app.config import settings
        if not settings.anthropic_api_key:
            return default

        ing_text = ", ".join(
            f"{i.get('qty', '')} {i.get('unit', '')} {i['name']}".strip()
            for i in ingredients
        )

        prompt = (
            f"Estimate nutrition per serving for this recipe: {title}. "
            f"Serves {servings}. Ingredients: {ing_text}. "
            f"Reply ONLY with a JSON object with integer keys: cals, protein, carbs, fat. "
            f'Example: {{"cals": 450, "protein": 35, "carbs": 40, "fat": 12}}'
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return default
    except Exception as exc:
        logger.warning("card_renderer: macro estimation failed — %s", exc)
        return default


def generate_card_steps(raw_content: str, title: str) -> tuple[list[str], str, str]:
    """Generate 5-6 detailed cooking steps, a chef's tip, and an enticing summary.

    Returns (steps_list, tip_string, summary_string). Falls back to ([], "", "") on failure.
    Single Claude Haiku call — cache all three outputs in raw_recipes on first run.
    """
    try:
        import anthropic
        from app.config import settings
        if not settings.anthropic_api_key or not raw_content:
            return [], "", ""

        prompt = (
            f"You are writing content for a premium recipe card for: {title}.\n\n"
            f"Source material (recipe transcript or post):\n{raw_content[:4000]}\n\n"
            f"Produce three things:\n\n"
            f"1. SUMMARY: 2-3 sentences that make someone want to cook this tonight. "
            f"Lead with the most appealing thing about it — flavour, speed, or a surprising technique. "
            f"Sound like a food editor, not a robot. Max 40 words.\n\n"
            f"2. STEPS: Exactly 5-6 detailed cooking steps, each 1-2 sentences. "
            f"Include specific temperatures, timings, and sensory cues "
            f"('until golden brown', 'when the oil shimmers'). "
            f"Cover every distinct action from prep to plate.\n\n"
            f"3. TIP: One chef's tip (max 20 words) — a technique insight, make-ahead note, "
            f"or substitution that genuinely helps.\n\n"
            f"Reply ONLY with valid JSON:\n"
            f'{{"summary": "...", "steps": ["step 1...", ...], "tip": "..."}}'
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
            return data.get("steps", []), data.get("tip", ""), data.get("summary", "")
        return [], "", ""
    except Exception as exc:
        logger.warning("card_renderer: card_steps generation failed — %s", exc)
        return [], "", ""


def _macro_pct(macros: dict) -> dict:
    """Compute rough calorie-share percentages for the macro bar."""
    p_cals = macros.get("protein", 0) * 4
    c_cals = macros.get("carbs", 0) * 4
    f_cals = macros.get("fat", 0) * 9
    total = p_cals + c_cals + f_cals or 1
    return {
        "protein_pct": round(p_cals / total * 100),
        "carbs_pct":   round(c_cals / total * 100),
        "fat_pct":     round(f_cals / total * 100),
    }


def render_recipe_cards(recipes: list[dict]) -> bytes:
    """Render a list of recipe dicts to a multi-page PDF (one card per page)."""
    from app.pdf_renderer import _render_with_playwright

    enriched = []
    for r in recipes:
        macros = r.get("macros") or {}
        enriched.append({**r, "macro_pct": _macro_pct(macros)})

    tmpl = _env.get_template("recipe_card.html")
    html_str = tmpl.render(
        recipes=enriched,
        difficulty_colors=DIFFICULTY_COLORS,
        dietary_abbr=DIETARY_ABBR,
    )
    return _render_with_playwright(html_str, week_label="Recipe Cards")

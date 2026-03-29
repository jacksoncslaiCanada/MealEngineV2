"""Ingredient name normalisation.

Converts a raw ingredient name (as extracted by Claude) into a canonical form
so that variant spellings and preparations map to the same key:

    "Chicken Thighs"    → "chicken"
    "chicken breast"    → "chicken"
    "diced onion"       → "onion"
    "extra-virgin olive oil" → "olive oil"
    "garlic cloves"     → "garlic"

Rules applied in order:
  1. Lower-case and strip whitespace
  2. Remove parenthetical notes  e.g. "(optional)"
  3. Strip leading preparation words  e.g. "diced", "chopped", "fresh"
  4. Strip trailing cut/form words    e.g. "cloves", "leaves", "strips"
  5. Collapse known synonyms          e.g. "bell pepper" → "pepper"
  6. Collapse plural to singular for common endings (-s, -es, -ies)

This is intentionally rules-based (no API call, no ML model) so it runs
in-process with zero latency and zero cost.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Preparation prefixes to strip
# e.g. "freshly ground black pepper" → "black pepper"
# ---------------------------------------------------------------------------
_PREP_PREFIXES = {
    "fresh", "freshly", "dried", "frozen", "cooked", "raw", "whole",
    "large", "medium", "small", "extra", "extra-large", "extra-virgin",
    "finely", "roughly", "coarsely", "thinly", "thickly",
    "diced", "chopped", "minced", "sliced", "grated", "shredded",
    "peeled", "deveined", "trimmed", "pitted", "seeded", "halved",
    "quartered", "crushed", "crumbled", "melted", "softened", "toasted",
    "roasted", "grilled", "steamed", "blanched", "sautéed", "sauteed",
    "packed", "heaped", "level", "ground", "powdered", "instant",
    "low-sodium", "reduced-fat", "full-fat", "unsalted", "salted",
    "uncooked", "boneless", "skinless", "lean",
}

# ---------------------------------------------------------------------------
# Trailing form/cut words to strip
# e.g. "garlic cloves" → "garlic", "chicken thighs" → "chicken"
# ---------------------------------------------------------------------------
_TRAILING_WORDS = {
    "clove", "cloves", "leaf", "leaves", "sprig", "sprigs",
    "stalk", "stalks", "slice", "slices", "strip", "strips",
    "chunk", "chunks", "piece", "pieces", "cube", "cubes",
    "floret", "florets", "wedge", "wedges",
    "thigh", "thighs", "breast", "breasts", "wing", "wings",
    "fillet", "fillets", "loin", "loins", "chop", "chops",
    "cutlet", "cutlets", "leg", "legs",
    "steak", "steaks",
    "powder", "flakes", "flake", "seeds", "seed",
    "zest", "juice",
}

# ---------------------------------------------------------------------------
# Synonym map — map any key to its canonical value
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, str] = {
    # peppers
    "bell pepper": "pepper",
    "capsicum": "pepper",
    "chilli": "chili",
    "chilli pepper": "chili",
    "chili pepper": "chili",
    "red chilli": "chili",
    "green chilli": "chili",
    "red pepper": "pepper",
    "green pepper": "pepper",
    "yellow pepper": "pepper",
    # alliums
    "spring onion": "scallion",
    "green onion": "scallion",
    "shallot": "shallot",
    # tomatoes
    "cherry tomato": "tomato",
    "plum tomato": "tomato",
    "sun-dried tomato": "sun-dried tomato",
    "canned tomato": "tomato",
    "tinned tomato": "tomato",
    # stock / broth
    "chicken broth": "chicken stock",
    "beef broth": "beef stock",
    "vegetable broth": "vegetable stock",
    # cream / dairy
    "double cream": "heavy cream",
    "single cream": "light cream",
    "heavy whipping cream": "heavy cream",
    # fats & oils
    "vegetable oil": "oil",
    "sunflower oil": "oil",
    "canola oil": "oil",
    "rapeseed oil": "oil",
    # herbs
    "fresh coriander": "coriander",
    "fresh parsley": "parsley",
    "fresh basil": "basil",
    "fresh thyme": "thyme",
    "fresh rosemary": "rosemary",
    "cilantro": "coriander",
    # pasta / noodles
    "egg noodle": "egg noodles",
    "rice noodle": "rice noodles",
    # legumes
    "chickpea": "chickpeas",
    "garbanzo bean": "chickpeas",
    "garbanzo": "chickpeas",
    # misc
    "plain flour": "flour",
    "all-purpose flour": "flour",
    "self-raising flour": "flour",
    "cornflour": "cornstarch",
    "corn flour": "cornstarch",
    "bicarbonate of soda": "baking soda",
    "natural yogurt": "yogurt",
    "natural yoghurt": "yogurt",
    "greek yogurt": "yogurt",
    "greek yoghurt": "yogurt",
    "sour cream": "sour cream",
    "passata": "tomato puree",
    "tomato paste": "tomato paste",
    "tomato purée": "tomato puree",
}


def normalise_ingredient(name: str) -> str:
    """Return the canonical form of an ingredient name.

    >>> normalise_ingredient("Chicken Thighs")
    'chicken'
    >>> normalise_ingredient("extra-virgin olive oil")
    'olive oil'
    >>> normalise_ingredient("finely diced onion")
    'onion'
    >>> normalise_ingredient("garlic cloves")
    'garlic'
    """
    # 1. Lower-case, collapse whitespace
    text = re.sub(r"\s+", " ", name.lower().strip())

    # 2. Remove parenthetical notes
    text = re.sub(r"\(.*?\)", "", text).strip()

    # 3. Check synonym map before stripping words (longest-match first)
    if text in _SYNONYMS:
        return _SYNONYMS[text]

    # 4. Strip prep prefixes (iteratively — handles "freshly ground")
    words = text.split()
    while words and words[0] in _PREP_PREFIXES:
        words.pop(0)

    # 5. Strip trailing form/cut words
    while words and words[-1] in _TRAILING_WORDS:
        words.pop()

    text = " ".join(words)

    # 6. Check synonym map again after stripping
    if text in _SYNONYMS:
        return _SYNONYMS[text]

    # 7. Simple pluralisation: strip trailing -s/-es for common patterns
    #    Only apply to single-word results to avoid false positives
    if " " not in text and len(text) > 4:
        if text.endswith("ies") and len(text) > 5:
            text = text[:-3] + "y"   # "berries" → "berry"
        elif text.endswith("ves") and len(text) > 5:
            text = text[:-3] + "f"   # "loaves" → "loaf"
        elif text.endswith("es") and len(text) > 4:
            # Only strip -es when the stem is at least 3 chars
            stem = text[:-2]
            if len(stem) >= 3 and stem[-1] not in "aeiou":
                text = stem             # "tomatoes" → "tomatoe" (avoid)
            # leave most -es words alone; the synonym map handles specific cases
        # Leave plain -s alone — "eggs" vs "egg" doesn't matter for search

    return text or name.lower().strip()

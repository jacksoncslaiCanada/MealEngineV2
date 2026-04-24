"""Theme pack definitions for Tier 1 meal packs.

Each ThemePack describes one $4.99 product: a 4-page PDF containing a
cover page and 3 recipe cards selected contextually by Claude.

To activate a placeholder:
  1. Set active=True
  2. Fill in name, tagline, description, and selection_hint
  3. Choose an accent_color
  4. Add its Gumroad product ID to Railway env vars as
     GUMROAD_THEME_<SLUG_UPPER>  (e.g. GUMROAD_THEME_ASIAN_KITCHEN)
  5. Run POST /internal/generate-theme-packs to pre-generate its PDF
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThemePack:
    slug: str            # filename-safe ID, used for storage + Gumroad mapping
    name: str            # display name on cover page
    tagline: str         # one-line hook shown large on cover
    description: str     # 2-3 sentences for cover page body text
    selection_hint: str  # tells Claude what to look for when picking 3 recipes
    accent_color: str    # hex color for cover page accents
    cuisine_keywords: tuple[str, ...] = field(default_factory=tuple)
    # Soft pre-filter: if ≥15 DB recipes match any of these cuisine values,
    # Claude receives only that smaller pool (more focused, fewer irrelevant candidates).
    # Falls back to full pool if not enough matches. Leave empty for broad themes.
    active: bool = True  # False = placeholder, excluded from generation


THEME_PACKS: list[ThemePack] = [

    # ── Active themes ──────────────────────────────────────────────────────────

    ThemePack(
        slug="asian-kitchen",
        name="Asian Kitchen",
        tagline="Bold, fragrant flavours from across Asia.",
        description=(
            "From silky Japanese ramen to fiery Korean bulgogi and fragrant Thai curries, "
            "this pack brings the depth and variety of Asian cooking into your weeknight routine. "
            "Each recipe is approachable, uses easy-to-find ingredients, and delivers restaurant-quality results."
        ),
        selection_hint=(
            "Select recipes inspired by East or Southeast Asian cuisines — Chinese, Japanese, Korean, "
            "Thai, Vietnamese, Filipino, or similar. Prioritise dishes where soy sauce, ginger, sesame, "
            "miso, coconut milk, fish sauce, or chilli are central flavours. Avoid fusion dishes where "
            "the Asian influence is superficial."
        ),
        accent_color="#c2522a",
        cuisine_keywords=("Asian", "Chinese", "Japanese", "Korean", "Thai", "Vietnamese", "Filipino", "Indian"),
    ),

    ThemePack(
        slug="mexican-fiesta",
        name="Mexican Fiesta",
        tagline="Vibrant, bold, and made for sharing.",
        description=(
            "Tacos, enchiladas, salsas, and slow-cooked meats bursting with colour and spice. "
            "Mexican cooking is generous, communal, and endlessly satisfying — perfect for family dinners "
            "or relaxed weekend gatherings where everyone builds their own plate."
        ),
        selection_hint=(
            "Select recipes with clear Mexican or Tex-Mex character. Look for dishes featuring corn tortillas, "
            "black or pinto beans, chipotle, cumin, lime, avocado, jalapeño, cilantro, or slow-cooked meats "
            "like carnitas or barbacoa. Prioritise flavourful and shareable dishes."
        ),
        accent_color="#2a8a3a",
        cuisine_keywords=("Mexican", "Tex-Mex", "Latin"),
    ),

    ThemePack(
        slug="light-and-fresh",
        name="Light & Fresh",
        tagline="Clean, nourishing meals that don't feel like a compromise.",
        description=(
            "Bright salads, lean proteins, and vegetable-forward dishes that are as satisfying as they are good "
            "for you. These recipes prove that eating light doesn't mean eating less — every plate is packed "
            "with flavour, colour, and ingredients that leave you feeling energised."
        ),
        selection_hint=(
            "Select recipes that are genuinely light and health-conscious — lean proteins (chicken breast, fish, "
            "tofu, legumes), lots of vegetables, salads with substance, grain bowls, or light soups. "
            "Avoid anything heavy, cream-based, or carb-dense. Dietary tags like 'gluten-free', 'dairy-free', "
            "or 'vegetarian' are a good signal but not required."
        ),
        accent_color="#4a8a5a",
        cuisine_keywords=(),  # broad theme — no cuisine pre-filter, rely on Claude
    ),

    ThemePack(
        slug="quick-cook",
        name="Quick Cook",
        tagline="Dinner on the table in 30 minutes or less.",
        description=(
            "No lengthy marinades, no complicated techniques — just fast, flavourful dinners designed for busy "
            "weeknights. These three recipes each come together in 30 minutes or less without sacrificing "
            "the satisfaction of a proper home-cooked meal."
        ),
        selection_hint=(
            "Select recipes with a total prep and cook time of 30 minutes or less. Look for dishes with "
            "short ingredient lists, minimal chopping, one-pan or one-pot methods, or fast-cooking proteins "
            "like shrimp, thin chicken cutlets, eggs, or canned legumes. Avoid anything requiring marinating, "
            "braising, or long oven time."
        ),
        accent_color="#d4762a",
        cuisine_keywords=(),  # broad theme — no cuisine pre-filter
    ),

    ThemePack(
        slug="comfort-food",
        name="Comfort Food",
        tagline="Hearty, warming dishes that feel like a hug.",
        description=(
            "When you want something rich, filling, and deeply satisfying, this is the pack to reach for. "
            "Think slow-cooked stews, golden baked pastas, crispy roasts, and indulgent but achievable "
            "classics that the whole family will ask for again and again."
        ),
        selection_hint=(
            "Select recipes that are hearty, warming, and indulgent — think slow braises, creamy pastas, "
            "roast meats, shepherd's pie, pot pies, chilli, mac and cheese, or similar. The dish should feel "
            "substantial and emotionally satisfying. Avoid anything light, salad-like, or diet-oriented."
        ),
        accent_color="#8b4a2a",
        cuisine_keywords=(),  # broad theme — no cuisine pre-filter
    ),

    # ── Placeholders — set active=True and fill in details when ready ──────────

    ThemePack(
        slug="mediterranean",
        name="Mediterranean",
        tagline="Sun-drenched flavours from the Mediterranean coast.",
        description="",
        selection_hint="",
        accent_color="#2a6b9c",
        active=False,
    ),

    ThemePack(
        slug="italian-classics",
        name="Italian Classics",
        tagline="Timeless Italian recipes done properly.",
        description="",
        selection_hint="",
        accent_color="#8b2a2a",
        active=False,
    ),

    ThemePack(
        slug="breakfast-brunch",
        name="Breakfast & Brunch",
        tagline="Weekend mornings, elevated.",
        description="",
        selection_hint="",
        accent_color="#d4a02a",
        active=False,
    ),

    ThemePack(
        slug="budget-friendly",
        name="Budget Friendly",
        tagline="Maximum flavour, minimum spend.",
        description="",
        selection_hint="",
        accent_color="#5a7a5a",
        active=False,
    ),

    ThemePack(
        slug="date-night",
        name="Date Night",
        tagline="Impressive recipes worth pulling out the good plates for.",
        description="",
        selection_hint="",
        accent_color="#4a2a6b",
        active=False,
    ),
]

# Lookup helpers
THEME_BY_SLUG: dict[str, ThemePack] = {t.slug: t for t in THEME_PACKS}
ACTIVE_THEMES: list[ThemePack] = [t for t in THEME_PACKS if t.active]

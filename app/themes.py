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

    ThemePack(
        slug="mediterranean",
        name="Mediterranean",
        tagline="Sun-drenched flavours from the shores of the Mediterranean.",
        description=(
            "Olive oil, fresh herbs, grilled fish, and vibrant vegetables — Mediterranean cooking is built "
            "on simplicity and the finest ingredients. From Greek salads and Turkish kebabs to Moroccan-spiced "
            "lamb, these three recipes capture the relaxed, flavour-forward spirit of coastal Mediterranean cuisine."
        ),
        selection_hint=(
            "Select recipes inspired by Mediterranean coastal cuisines — Greek, Italian, Spanish, Turkish, "
            "Moroccan, Lebanese, or similar. Look for dishes featuring olive oil, lemon, garlic, tomatoes, "
            "fresh herbs (basil, oregano, parsley, mint), legumes, grilled seafood or lamb, feta, or aubergine. "
            "Avoid heavy cream-based or north-European dishes."
        ),
        accent_color="#2a6b9c",
        cuisine_keywords=("Mediterranean", "Greek", "Spanish", "Turkish", "Moroccan", "Lebanese"),
    ),

    ThemePack(
        slug="italian-classics",
        name="Italian Classics",
        tagline="Timeless Italian recipes done properly.",
        description=(
            "From slow-simmered ragù to golden risotto and hand-stretched pizza, Italian cooking rewards "
            "patience and simplicity in equal measure. These three recipes are the kind of dishes Italian "
            "nonnas have been making for generations — honest ingredients, classic technique, and flavours "
            "that never go out of style."
        ),
        selection_hint=(
            "Select recipes with clear Italian character — pasta dishes (carbonara, cacio e pepe, puttanesca, "
            "arrabbiata, bolognese, amatriciana), risotto, pizza, osso buco, saltimbocca, or similar. "
            "Look for recipes where the Italian technique or ingredient combination is central, not superficial. "
            "Avoid dishes where 'Italian' is just a seasoning tweak on a non-Italian base."
        ),
        accent_color="#8b2a2a",
        cuisine_keywords=("Italian",),
    ),

    ThemePack(
        slug="middle-eastern",
        name="Middle Eastern",
        tagline="Ancient spices, vibrant flavours, generous tables.",
        description=(
            "Za'atar, sumac, tahini, pomegranate — Middle Eastern cooking layers spice and texture in ways "
            "that feel both ancient and excitingly fresh. From smoky baba ganoush to slow-cooked lamb and "
            "silky hummus, these recipes bring the warmth and generosity of the region's table to your kitchen."
        ),
        selection_hint=(
            "Select recipes from Middle Eastern cuisines — Lebanese, Israeli, Persian, Turkish, Egyptian, "
            "Jordanian, or similar. Look for dishes featuring tahini, za'atar, sumac, pomegranate molasses, "
            "harissa, preserved lemon, chickpeas, lamb, flatbreads, or heavily spiced rice. Shakshuka, "
            "falafel, kibbeh, kofta, and mezze-style dishes are strong choices. Avoid generic 'spiced' dishes "
            "with no clear regional identity."
        ),
        accent_color="#c4823a",
        cuisine_keywords=("Middle Eastern", "Lebanese", "Persian", "Turkish", "Israeli", "Moroccan", "Egyptian"),
    ),

    ThemePack(
        slug="high-protein",
        name="High Protein",
        tagline="Fuel your body without compromising on flavour.",
        description=(
            "Built around lean meats, eggs, legumes, and dairy, these recipes deliver 30g or more of protein "
            "per serving without relying on supplements or sacrificing taste. Whether you're training hard or "
            "just trying to eat smarter, each dish is satisfying, nutritionally dense, and genuinely delicious."
        ),
        selection_hint=(
            "Select recipes that are genuinely high in protein — 25g or more per serving. Prioritise lean "
            "chicken breast or thighs, turkey, salmon or tuna, eggs, Greek yoghurt, cottage cheese, lentils, "
            "chickpeas, tofu, or tempeh as the primary protein source. The dish should feel substantial and "
            "satisfying, not diet food. Avoid recipes where protein is incidental or the serving is small."
        ),
        accent_color="#4a6b8a",
        cuisine_keywords=(),  # broad theme — no cuisine pre-filter
    ),

    ThemePack(
        slug="one-pan",
        name="One Pan",
        tagline="Maximum flavour, minimal washing up.",
        description=(
            "One pan, one tray, or one pot — these recipes are designed so everything cooks together, "
            "letting the flavours meld while you get on with your evening. Less mess, less stress, and "
            "results that taste like you worked much harder than you did."
        ),
        selection_hint=(
            "Select recipes that genuinely cook entirely in a single pan, skillet, sheet tray, or pot — "
            "no separate sides requiring their own cookware. Look for sheet pan dinners, one-pot pastas, "
            "skillet meals, traybakes, or one-pot braises where proteins and vegetables cook together. "
            "The single-vessel constraint should be real and central to the recipe, not incidental."
        ),
        accent_color="#7a5a3a",
        cuisine_keywords=(),  # broad theme — no cuisine pre-filter
    ),
]

# Lookup helpers
THEME_BY_SLUG: dict[str, ThemePack] = {t.slug: t for t in THEME_PACKS}
ACTIVE_THEMES: list[ThemePack] = [t for t in THEME_PACKS if t.active]

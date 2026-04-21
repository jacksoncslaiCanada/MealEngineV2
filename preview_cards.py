"""
Standalone recipe card preview script — no database required.

Usage:
    python preview_cards.py

Flags (env vars):
    GENERATE_IMAGES=1    Call DALL-E 3 to generate food photos (~$0.20 for 5 cards).
                         Requires OPENAI_API_KEY in your .env or environment.
                         Default: off (placeholder image shown instead).

    ESTIMATE_MACROS=1    Call Claude Haiku to estimate macros per recipe.
                         Requires ANTHROPIC_API_KEY in your .env or environment.
                         Default: off (macro values hardcoded below).

    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chrome
                         Override the Chromium binary path (needed in some dev envs).

Output:
    preview_cards.pdf in the project root.

Edit app/templates/recipe_card.html and re-run to iterate on design.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.card_renderer import generate_food_image, estimate_macros, render_recipe_cards

# ---------------------------------------------------------------------------
# 5 test recipes — covers breakfast, dinner, multiple cuisines, tag combos
# ---------------------------------------------------------------------------

RECIPES: list[dict] = [
    {
        "title": "Honey Garlic Salmon",
        "cuisine": "Asian",
        "difficulty": "easy",
        "prep_time": 25,
        "servings": 4,
        "dietary_tags": ["gluten-free", "dairy-free"],
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "quick_steps": [
            "Whisk together 3 tbsp honey, 3 minced garlic cloves, 2 tbsp soy sauce, and 1 tsp sesame oil to make the glaze.",
            "Heat 1 tbsp olive oil in a skillet over medium-high. Sear 4 salmon fillets skin-side down for 4 minutes until crispy.",
            "Flip salmon, pour the glaze over the top, and cook 3–4 minutes, spooning glaze continuously until caramelised.",
            "Serve over steamed jasmine rice. Garnish with sliced lemon and spring onions.",
        ],
        "ingredients": [
            {"name": "salmon fillets", "qty": "4", "unit": ""},
            {"name": "honey", "qty": "3", "unit": "tbsp"},
            {"name": "garlic cloves, minced", "qty": "3", "unit": ""},
            {"name": "soy sauce", "qty": "2", "unit": "tbsp"},
            {"name": "sesame oil", "qty": "1", "unit": "tsp"},
            {"name": "olive oil", "qty": "1", "unit": "tbsp"},
            {"name": "lemon", "qty": "1", "unit": ""},
            {"name": "spring onions", "qty": "2", "unit": "stalks"},
            {"name": "jasmine rice", "qty": "", "unit": "to serve"},
        ],
        "components": [
            {"role": "base",    "label": "Jasmine Rice"},
            {"role": "flavor",  "label": "Honey Garlic Glaze"},
            {"role": "protein", "label": "Salmon fillets"},
        ],
        "macros": {"cals": 420, "protein": 38, "carbs": 32, "fat": 14},
    },
    {
        "title": "Banana Oat Pancakes",
        "cuisine": "",
        "difficulty": "easy",
        "prep_time": 20,
        "servings": 4,
        "dietary_tags": ["gluten-free", "vegetarian"],
        "url": None,
        "quick_steps": [
            "Mash 2 ripe bananas in a large bowl until smooth. Mix in 1 cup rolled oats, 2 eggs, and a pinch of salt.",
            "Heat a non-stick pan over medium heat and lightly grease. Scoop ¼ cup batter per pancake.",
            "Cook 2–3 minutes until bubbles form on the surface, then flip and cook a further 2 minutes until golden.",
            "Stack on plates and serve with fresh berries and a drizzle of maple syrup.",
        ],
        "ingredients": [
            {"name": "ripe bananas", "qty": "2", "unit": ""},
            {"name": "rolled oats", "qty": "1", "unit": "cup"},
            {"name": "eggs", "qty": "2", "unit": ""},
            {"name": "maple syrup", "qty": "2", "unit": "tbsp"},
            {"name": "mixed berries", "qty": "1", "unit": "cup"},
            {"name": "coconut oil", "qty": "1", "unit": "tsp"},
        ],
        "components": [
            {"role": "base",    "label": "Oat Batter"},
            {"role": "flavor",  "label": "Maple & Berry Topping"},
        ],
        "macros": {"cals": 280, "protein": 9, "carbs": 48, "fat": 7},
    },
    {
        "title": "Beef & Broccoli Stir-fry",
        "cuisine": "Asian",
        "difficulty": "medium",
        "prep_time": 30,
        "servings": 4,
        "dietary_tags": ["dairy-free"],
        "url": None,
        "quick_steps": [
            "Slice 500 g beef sirloin thinly against the grain. Marinate 10 min in 2 tbsp soy sauce, 1 tbsp oyster sauce, 1 tsp cornstarch.",
            "Blanch 2 cups broccoli florets in boiling water for 90 seconds; drain. Mix stir-fry sauce: 3 tbsp soy, 1 tbsp oyster, 1 tsp sesame oil, 1 tsp sugar, 2 tsp cornstarch.",
            "Heat wok until smoking hot. Stir-fry beef in batches 2 minutes each. Add 3 cloves garlic and 1 tsp ginger.",
            "Return all beef, add broccoli and sauce. Toss 1–2 minutes until glossy. Serve over steamed rice.",
        ],
        "ingredients": [
            {"name": "beef sirloin, thinly sliced", "qty": "500", "unit": "g"},
            {"name": "broccoli florets", "qty": "2", "unit": "cups"},
            {"name": "garlic cloves", "qty": "3", "unit": ""},
            {"name": "fresh ginger", "qty": "1", "unit": "tsp"},
            {"name": "soy sauce", "qty": "5", "unit": "tbsp"},
            {"name": "oyster sauce", "qty": "2", "unit": "tbsp"},
            {"name": "sesame oil", "qty": "1", "unit": "tsp"},
            {"name": "cornstarch", "qty": "3", "unit": "tsp"},
        ],
        "components": [
            {"role": "base",    "label": "Steamed Rice"},
            {"role": "flavor",  "label": "Oyster Soy Stir-fry Sauce"},
            {"role": "protein", "label": "Beef sirloin"},
        ],
        "macros": {"cals": 390, "protein": 34, "carbs": 28, "fat": 16},
    },
    {
        "title": "Creamy Tomato Pasta",
        "cuisine": "Italian",
        "difficulty": "easy",
        "prep_time": 25,
        "servings": 4,
        "dietary_tags": ["vegetarian"],
        "url": None,
        "quick_steps": [
            "Cook 400 g penne in salted boiling water until al dente. Reserve 1 cup pasta water before draining.",
            "Sauté 1 diced onion in olive oil 5 minutes. Add 3 garlic cloves, cook 1 minute. Add 400 g crushed tomatoes; simmer 10 minutes.",
            "Stir in ½ cup heavy cream and season generously with salt, pepper, and dried basil.",
            "Toss pasta with sauce, adding pasta water to loosen. Finish with grated Parmesan and fresh basil leaves.",
        ],
        "ingredients": [
            {"name": "penne pasta", "qty": "400", "unit": "g"},
            {"name": "crushed tomatoes", "qty": "400", "unit": "g"},
            {"name": "heavy cream", "qty": "½", "unit": "cup"},
            {"name": "onion, diced", "qty": "1", "unit": ""},
            {"name": "garlic cloves", "qty": "3", "unit": ""},
            {"name": "Parmesan, grated", "qty": "½", "unit": "cup"},
            {"name": "olive oil", "qty": "2", "unit": "tbsp"},
            {"name": "fresh basil", "qty": "", "unit": "handful"},
        ],
        "components": [
            {"role": "base",    "label": "Penne Pasta"},
            {"role": "flavor",  "label": "Creamy Tomato Sauce"},
            {"role": "protein", "label": "Parmesan"},
        ],
        "macros": {"cals": 510, "protein": 16, "carbs": 72, "fat": 18},
    },
    {
        "title": "Mini Chicken Tacos",
        "cuisine": "Mexican",
        "difficulty": "easy",
        "prep_time": 25,
        "servings": 4,
        "dietary_tags": ["dairy-free"],
        "url": None,
        "quick_steps": [
            "Season 500 g chicken thighs with 1 tsp each cumin, paprika, garlic powder, plus salt and pepper.",
            "Pan-fry over medium-high heat for 6 minutes each side until cooked through and nicely charred.",
            "Rest 5 minutes, then shred with two forks. Warm 12 small flour tortillas in a dry pan, 30 seconds per side.",
            "Assemble: chicken, diced tomato, shredded lettuce, sliced avocado, and a squeeze of fresh lime.",
        ],
        "ingredients": [
            {"name": "chicken thighs", "qty": "500", "unit": "g"},
            {"name": "small flour tortillas", "qty": "12", "unit": ""},
            {"name": "tomatoes, diced", "qty": "2", "unit": ""},
            {"name": "lettuce, shredded", "qty": "1", "unit": "cup"},
            {"name": "avocado", "qty": "1", "unit": ""},
            {"name": "lime", "qty": "2", "unit": ""},
            {"name": "cumin", "qty": "1", "unit": "tsp"},
            {"name": "paprika", "qty": "1", "unit": "tsp"},
        ],
        "components": [
            {"role": "base",    "label": "Flour Tortillas"},
            {"role": "flavor",  "label": "Cumin Paprika Rub"},
            {"role": "protein", "label": "Chicken thighs"},
        ],
        "macros": {"cals": 440, "protein": 31, "carbs": 42, "fat": 17},
    },
]

# ---------------------------------------------------------------------------
# Optional: generate AI images and/or estimate macros via API
# ---------------------------------------------------------------------------

GENERATE_IMAGES  = os.getenv("GENERATE_IMAGES", "0") == "1"
ESTIMATE_MACROS  = os.getenv("ESTIMATE_MACROS", "0") == "1"

if GENERATE_IMAGES or ESTIMATE_MACROS:
    # Load .env so API keys are available
    from dotenv import load_dotenv
    load_dotenv()

for recipe in RECIPES:
    if GENERATE_IMAGES:
        print(f"  Generating image for '{recipe['title']}'…")
        recipe["image_url"] = generate_food_image(
            recipe["title"],
            recipe.get("cuisine", ""),
            recipe["ingredients"],
        )
    else:
        recipe.setdefault("image_url", None)

    if ESTIMATE_MACROS:
        print(f"  Estimating macros for '{recipe['title']}'…")
        recipe["macros"] = estimate_macros(
            recipe["title"],
            recipe["ingredients"],
            recipe.get("servings", 4),
        )

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

OUTPUT = Path(__file__).parent / "preview_cards.pdf"

print("Rendering recipe cards…")
try:
    pdf_bytes = render_recipe_cards(RECIPES)
    OUTPUT.write_bytes(pdf_bytes)
    print(f"Done — {len(pdf_bytes) // 1024} KB written to {OUTPUT}")
    print()
    print("Open with:  xdg-open preview_cards.pdf   (Linux)")
    print("            open preview_cards.pdf        (macOS)")
    print()
    print("Re-run with flags to activate AI features:")
    print("  GENERATE_IMAGES=1 python preview_cards.py   # DALL-E 3 food photos (~$0.20)")
    print("  ESTIMATE_MACROS=1 python preview_cards.py   # Claude Haiku macro estimates")
except Exception as exc:
    print(f"ERROR: {exc}")
    raise

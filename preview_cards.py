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
        "card_steps": [
            "Pat 4 salmon fillets completely dry with paper towels — this is the key to a golden crust. Season both sides generously with salt and black pepper.",
            "In a small bowl, whisk together 3 tbsp honey, 3 minced garlic cloves, 2 tbsp soy sauce, and 1 tsp sesame oil until the honey dissolves. Set the glaze aside.",
            "Heat 1 tbsp olive oil in a large non-stick skillet over medium-high until it just starts to shimmer. Place salmon skin-side down and press gently for 10 seconds so it doesn't curl.",
            "Cook without moving for 4 minutes until the skin is deeply golden and crispy. You'll see the flesh turn opaque about halfway up — that's your cue to flip.",
            "Flip the fillets, reduce heat to medium, and pour the honey garlic glaze over the top. Cook 3–4 minutes, spooning the glaze over the fish continuously as it caramelises.",
            "Transfer to plates over steamed jasmine rice. Spoon any remaining pan glaze over the top. Garnish with sliced lemon and spring onions and serve immediately.",
        ],
        "card_tip": "Don't move the salmon while it sears — those 4 undisturbed minutes build the crispy crust.",
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
        "card_steps": [
            "Peel 2 very ripe bananas (brown-spotted ones are sweetest) and mash thoroughly in a large bowl with a fork until almost no lumps remain.",
            "Add 1 cup rolled oats, 2 eggs, a pinch of salt, and ½ tsp vanilla extract. Stir until combined. The batter will be thick — that's correct. Let it rest 3 minutes so the oats absorb moisture.",
            "Heat a non-stick pan over medium heat and add a small piece of butter or a spray of oil. When it foams, the pan is ready.",
            "Scoop ¼ cup batter per pancake and spread gently into a round. Cook 2–3 minutes until bubbles break on the surface and the edges look set.",
            "Flip once and cook a further 2 minutes until the underside is golden. These pancakes are denser than regular ones — don't rush them on high heat.",
            "Stack on warm plates. Serve with fresh mixed berries, a dollop of Greek yogurt, and a drizzle of maple syrup.",
        ],
        "card_tip": "The riper the bananas, the sweeter the pancakes — no extra sugar needed.",
        "ingredients": [
            {"name": "ripe bananas", "qty": "2", "unit": ""},
            {"name": "rolled oats", "qty": "1", "unit": "cup"},
            {"name": "eggs", "qty": "2", "unit": ""},
            {"name": "vanilla extract", "qty": "½", "unit": "tsp"},
            {"name": "maple syrup", "qty": "2", "unit": "tbsp"},
            {"name": "mixed berries", "qty": "1", "unit": "cup"},
            {"name": "Greek yogurt", "qty": "", "unit": "to serve"},
        ],
        "components": [
            {"role": "base",    "label": "Oat & Banana Batter"},
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
        "card_steps": [
            "Slice 500 g beef sirloin as thinly as possible against the grain — partially freezing the meat for 20 minutes makes this much easier. Marinate in 2 tbsp soy sauce, 1 tbsp oyster sauce, and 1 tsp cornstarch for at least 10 minutes.",
            "While the beef marinates, mix your stir-fry sauce: 3 tbsp soy sauce, 1 tbsp oyster sauce, 1 tsp sesame oil, 1 tsp sugar, 2 tsp cornstarch, and 3 tbsp water. Stir until smooth.",
            "Bring a pot of water to a boil. Blanch 2 cups broccoli florets for exactly 90 seconds — they should be bright green and just tender. Drain and set aside.",
            "Heat your wok over the highest heat possible until it begins to smoke. Add 1 tbsp oil, then stir-fry the beef in two batches, 90 seconds each, spreading it flat. Overcrowding steams instead of sears.",
            "Push the beef to one side. Add a splash of oil, then fry 3 minced garlic cloves and 1 tsp grated ginger for 20 seconds until fragrant.",
            "Add the broccoli back in, pour the sauce over everything, and toss vigorously for 1–2 minutes until the sauce thickens and coats the beef in a glossy sheen. Serve immediately over steamed rice.",
        ],
        "card_tip": "Cook the beef in batches on screaming-hot heat — crowding the pan makes it steam and turn grey.",
        "ingredients": [
            {"name": "beef sirloin, thinly sliced", "qty": "500", "unit": "g"},
            {"name": "broccoli florets", "qty": "2", "unit": "cups"},
            {"name": "garlic cloves", "qty": "3", "unit": ""},
            {"name": "fresh ginger, grated", "qty": "1", "unit": "tsp"},
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
        "card_steps": [
            "Bring a large pot of water to a rolling boil. Add 2 tsp salt — it should taste like mild seawater. Cook 400 g penne until al dente (usually 1 minute less than the packet says). Before draining, scoop out 1 full cup of pasta water.",
            "While the pasta cooks, heat 2 tbsp olive oil in a wide saucepan over medium. Add 1 finely diced onion and cook, stirring occasionally, for 5–6 minutes until soft and translucent.",
            "Add 3 thinly sliced garlic cloves and cook 1 minute more until fragrant. Pour in 400 g crushed tomatoes, stir well, and simmer uncovered for 10 minutes until slightly thickened.",
            "Reduce the heat to low and stir in ½ cup heavy cream. Season generously with salt, pepper, and a pinch of sugar if the tomatoes are acidic. Simmer gently for 2 minutes — don't boil or the cream may split.",
            "Drain the pasta and add directly to the sauce. Toss to coat, adding splashes of the reserved pasta water until the sauce clings silkily to every piece.",
            "Serve in warmed bowls. Finish with a generous handful of grated Parmesan, fresh basil leaves, and a crack of black pepper.",
        ],
        "card_tip": "Always save pasta water — its starch is what makes the sauce cling instead of pool at the bottom.",
        "ingredients": [
            {"name": "penne pasta", "qty": "400", "unit": "g"},
            {"name": "crushed tomatoes", "qty": "400", "unit": "g"},
            {"name": "heavy cream", "qty": "½", "unit": "cup"},
            {"name": "onion, finely diced", "qty": "1", "unit": ""},
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
        "card_steps": [
            "Trim 500 g chicken thighs of excess fat. Mix together 1 tsp each of cumin, smoked paprika, garlic powder, onion powder, plus ¾ tsp salt and ¼ tsp pepper. Coat the chicken thighs all over in the spice mix.",
            "Heat 1 tbsp oil in a heavy skillet over medium-high until shimmering. Add chicken and cook without moving for 5–6 minutes until deeply charred on the underside.",
            "Flip and cook another 5 minutes until the internal temperature reaches 74°C (165°F). Transfer to a plate and rest for 5 minutes — resting keeps it juicy.",
            "Use two forks to shred the chicken into thin strips, pulling with the grain. It should pull apart easily. Taste and adjust salt.",
            "Warm 12 small flour tortillas in a dry pan for 30 seconds each side, or wrap in a damp paper towel and microwave for 45 seconds.",
            "Set up a taco bar: shredded chicken, diced tomatoes, shredded lettuce, sliced avocado, fresh lime wedges, and hot sauce. Let everyone build their own.",
        ],
        "card_tip": "Rest the chicken before shredding — cut too soon and all the juices run out onto the board.",
        "ingredients": [
            {"name": "chicken thighs", "qty": "500", "unit": "g"},
            {"name": "small flour tortillas", "qty": "12", "unit": ""},
            {"name": "tomatoes, diced", "qty": "2", "unit": ""},
            {"name": "lettuce, shredded", "qty": "1", "unit": "cup"},
            {"name": "avocado", "qty": "1", "unit": ""},
            {"name": "lime", "qty": "2", "unit": ""},
            {"name": "cumin", "qty": "1", "unit": "tsp"},
            {"name": "smoked paprika", "qty": "1", "unit": "tsp"},
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

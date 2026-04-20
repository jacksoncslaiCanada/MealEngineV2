"""
Standalone PDF preview script — no database required.

Usage:
    python preview_pdf.py

Writes preview.pdf in the current directory.
Open it in any PDF viewer (Evince, Okular, Preview) — most auto-refresh
when the file changes, so just re-run the script to see updates.

Edit app/templates/meal_plan_pdf.html, re-run, repeat.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Make sure the app package is importable from the project root
sys.path.insert(0, str(Path(__file__).parent))

from app.pdf_renderer import render_pdf

# ---------------------------------------------------------------------------
# Sample data — edit freely to test different scenarios
# ---------------------------------------------------------------------------

DAYS = [
    {
        "day": "Monday",
        "breakfast": {
            "recipe_id": 1,
            "title": "Banana Oat Pancakes",
            "difficulty": "easy",
            "cuisine": "",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "prep_time": 20,
            "dietary_tags": ["gluten-free", "vegan"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Mash 2 ripe bananas in a bowl, then mix in 1 cup oats, 2 eggs, and a pinch of salt.",
                "Heat a non-stick pan over medium heat. Scoop ¼ cup batter per pancake and cook 2–3 min each side.",
                "Serve with maple syrup and fresh berries.",
            ],
            "ingredients": [
                {"name": "ripe bananas", "qty": "2", "unit": ""},
                {"name": "rolled oats", "qty": "1", "unit": "cup"},
                {"name": "eggs", "qty": "2", "unit": ""},
                {"name": "maple syrup", "qty": "2", "unit": "tbsp"},
                {"name": "mixed berries", "qty": "1", "unit": "cup"},
            ],
        },
        "lunch": {"title": "Leftovers: Sunday's Roast Chicken", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 2,
            "title": "Honey Garlic Salmon",
            "difficulty": "easy",
            "cuisine": "Asian",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "prep_time": 25,
            "dietary_tags": ["gluten-free", "dairy-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Whisk together 3 tbsp honey, 3 minced garlic cloves, 2 tbsp soy sauce, and 1 tsp sesame oil in a small bowl to make the glaze.",
                "Heat 1 tbsp olive oil in a large skillet over medium-high heat. Season 4 salmon fillets with salt and pepper, then sear skin-side down for 4 minutes until crispy.",
                "Flip salmon, pour the honey garlic glaze over the top, and cook for a further 3–4 minutes, spooning the glaze over continuously until caramelised.",
                "Serve immediately over steamed rice. Garnish with sliced lemon and chopped spring onions.",
            ],
            "ingredients": [
                {"name": "salmon fillets", "qty": "4", "unit": ""},
                {"name": "honey", "qty": "3", "unit": "tbsp"},
                {"name": "garlic cloves, minced", "qty": "3", "unit": ""},
                {"name": "soy sauce", "qty": "2", "unit": "tbsp"},
                {"name": "olive oil", "qty": "1", "unit": "tbsp"},
                {"name": "sesame oil", "qty": "1", "unit": "tsp"},
                {"name": "lemon", "qty": "1", "unit": ""},
                {"name": "spring onions", "qty": "2", "unit": "stalks"},
                {"name": "steamed rice", "qty": "", "unit": "to serve"},
            ],
        },
    },
    {
        "day": "Tuesday",
        "breakfast": {
            "recipe_id": 3,
            "title": "Scrambled Eggs on Toast",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 10,
            "dietary_tags": [],
            "spice_level": "mild",
            "servings": 2,
            "quick_steps": [
                "Beat 4 eggs with a splash of milk, salt, and pepper.",
                "Melt butter in a pan over low heat, add eggs, and stir gently until just set.",
                "Serve on toasted sourdough with a sprinkle of chives.",
            ],
            "ingredients": [
                {"name": "eggs", "qty": "4", "unit": ""},
                {"name": "butter", "qty": "1", "unit": "tbsp"},
                {"name": "milk", "qty": "2", "unit": "tbsp"},
                {"name": "sourdough bread", "qty": "2", "unit": "slices"},
                {"name": "chives", "qty": "", "unit": "to garnish"},
            ],
        },
        "lunch": {"title": "Leftovers: Honey Garlic Salmon", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 4,
            "title": "Chicken Fried Rice",
            "difficulty": "easy",
            "cuisine": "Asian",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "prep_time": 20,
            "dietary_tags": ["dairy-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Cook 1½ cups jasmine rice and set aside to cool slightly. Dice 2 chicken breasts into small pieces and season with salt, pepper, and 1 tbsp soy sauce.",
                "Heat 2 tbsp oil in a wok over high heat. Stir-fry chicken for 5–6 minutes until cooked. Push to the side, scramble in 2 eggs, then mix together.",
                "Add cooked rice and frozen peas to the wok. Drizzle over 2 tbsp soy sauce and 1 tsp sesame oil. Toss everything on high heat for 2–3 minutes. Serve topped with spring onions.",
            ],
            "ingredients": [
                {"name": "chicken breasts", "qty": "2", "unit": ""},
                {"name": "jasmine rice", "qty": "1.5", "unit": "cups"},
                {"name": "eggs", "qty": "2", "unit": ""},
                {"name": "frozen peas", "qty": "1", "unit": "cup"},
                {"name": "soy sauce", "qty": "3", "unit": "tbsp"},
                {"name": "sesame oil", "qty": "1", "unit": "tsp"},
                {"name": "vegetable oil", "qty": "2", "unit": "tbsp"},
                {"name": "spring onions", "qty": "3", "unit": "stalks"},
            ],
        },
    },
    {
        "day": "Wednesday",
        "breakfast": {
            "recipe_id": 5,
            "title": "Greek Yogurt Parfait",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 5,
            "dietary_tags": ["gluten-free"],
            "spice_level": "mild",
            "servings": 2,
            "quick_steps": [
                "Layer Greek yogurt, granola, and mixed berries in two glasses or bowls.",
                "Drizzle with honey and serve immediately.",
            ],
            "ingredients": [
                {"name": "Greek yogurt", "qty": "2", "unit": "cups"},
                {"name": "granola", "qty": "½", "unit": "cup"},
                {"name": "mixed berries", "qty": "1", "unit": "cup"},
                {"name": "honey", "qty": "1", "unit": "tbsp"},
            ],
        },
        "lunch": {"title": "Leftovers: Chicken Fried Rice", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 6,
            "title": "Beef & Broccoli Stir-fry",
            "difficulty": "medium",
            "cuisine": "Asian",
            "url": None,
            "prep_time": 30,
            "dietary_tags": ["dairy-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Slice 500g beef sirloin thinly against the grain. Marinate for 10 minutes in 2 tbsp soy sauce, 1 tbsp oyster sauce, and 1 tsp cornstarch.",
                "Blanch 2 cups broccoli florets in boiling water for 90 seconds, then drain. Mix sauce: 3 tbsp soy sauce, 1 tbsp oyster sauce, 1 tsp sesame oil, 1 tsp sugar, 2 tsp cornstarch.",
                "Heat wok until smoking. Stir-fry beef in batches for 2 minutes. Add garlic and ginger, then broccoli. Pour sauce over, toss 1–2 minutes until glossy. Serve with steamed rice.",
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
        },
    },
    {
        "day": "Thursday",
        "breakfast": {
            "recipe_id": 7,
            "title": "Avocado Toast with Poached Eggs",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 15,
            "dietary_tags": ["dairy-free"],
            "spice_level": "mild",
            "servings": 2,
            "quick_steps": [
                "Toast sourdough. Mash 1 avocado with lemon juice, salt, and chili flakes.",
                "Poach 2 eggs in simmering water with a splash of vinegar for 3 minutes.",
                "Spread avocado on toast, top with poached egg, season, and serve.",
            ],
            "ingredients": [
                {"name": "sourdough bread", "qty": "2", "unit": "slices"},
                {"name": "avocado", "qty": "1", "unit": ""},
                {"name": "eggs", "qty": "2", "unit": ""},
                {"name": "lemon juice", "qty": "1", "unit": "tsp"},
                {"name": "chili flakes", "qty": "", "unit": "pinch"},
            ],
        },
        "lunch": {"title": "Leftovers: Beef & Broccoli Stir-fry", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 8,
            "title": "Creamy Tomato Pasta",
            "difficulty": "easy",
            "cuisine": "Italian",
            "url": None,
            "prep_time": 25,
            "dietary_tags": ["vegetarian"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Cook 400g penne in salted boiling water until al dente. Reserve 1 cup pasta water before draining.",
                "Sauté diced onion in olive oil for 5 minutes. Add 3 garlic cloves, cook 1 minute. Add 400g crushed tomatoes and simmer 10 minutes.",
                "Stir in ½ cup heavy cream and season. Toss with pasta, adding pasta water to loosen. Finish with Parmesan and fresh basil.",
            ],
            "ingredients": [
                {"name": "penne pasta", "qty": "400", "unit": "g"},
                {"name": "crushed tomatoes", "qty": "400", "unit": "g"},
                {"name": "heavy cream", "qty": "½", "unit": "cup"},
                {"name": "onion, diced", "qty": "1", "unit": ""},
                {"name": "garlic cloves", "qty": "3", "unit": ""},
                {"name": "Parmesan, grated", "qty": "½", "unit": "cup"},
                {"name": "fresh basil", "qty": "", "unit": "handful"},
            ],
        },
    },
    {
        "day": "Friday",
        "breakfast": {
            "recipe_id": 9,
            "title": "Overnight Oats with Berries",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 5,
            "dietary_tags": ["vegan", "gluten-free"],
            "spice_level": "mild",
            "servings": 2,
            "quick_steps": [
                "Combine ½ cup oats, ¾ cup oat milk, 1 tbsp chia seeds, and 1 tsp honey. Stir well.",
                "Refrigerate overnight (or at least 4 hours).",
                "Top with fresh berries and a drizzle of honey before serving.",
            ],
            "ingredients": [
                {"name": "rolled oats", "qty": "½", "unit": "cup"},
                {"name": "oat milk", "qty": "¾", "unit": "cup"},
                {"name": "chia seeds", "qty": "1", "unit": "tbsp"},
                {"name": "mixed berries", "qty": "½", "unit": "cup"},
                {"name": "honey", "qty": "1", "unit": "tsp"},
            ],
        },
        "lunch": {"title": "Leftovers: Creamy Tomato Pasta", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 10,
            "title": "Mini Chicken Tacos",
            "difficulty": "easy",
            "cuisine": "Mexican",
            "url": None,
            "prep_time": 25,
            "dietary_tags": ["dairy-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Season 500g chicken thighs with cumin, paprika, garlic powder, salt, and pepper. Pan-fry over medium-high for 6 minutes each side until cooked through.",
                "Rest 5 minutes then shred with two forks. Warm small flour tortillas in a dry pan.",
                "Assemble tacos: chicken, diced tomato, shredded lettuce, and a squeeze of lime. Serve immediately.",
            ],
            "ingredients": [
                {"name": "chicken thighs", "qty": "500", "unit": "g"},
                {"name": "small flour tortillas", "qty": "12", "unit": ""},
                {"name": "tomatoes, diced", "qty": "2", "unit": ""},
                {"name": "lettuce, shredded", "qty": "1", "unit": "cup"},
                {"name": "lime", "qty": "2", "unit": ""},
                {"name": "cumin", "qty": "1", "unit": "tsp"},
                {"name": "paprika", "qty": "1", "unit": "tsp"},
            ],
        },
    },
    {
        "day": "Saturday",
        "breakfast": {
            "recipe_id": 11,
            "title": "Blueberry Smoothie Bowl",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 10,
            "dietary_tags": ["vegan", "gluten-free"],
            "spice_level": "mild",
            "servings": 2,
            "quick_steps": [
                "Blend 1 cup frozen blueberries, 1 frozen banana, and ½ cup oat milk until thick and smooth.",
                "Pour into bowls and add toppings: granola, sliced banana, and a drizzle of honey.",
            ],
            "ingredients": [
                {"name": "frozen blueberries", "qty": "1", "unit": "cup"},
                {"name": "frozen banana", "qty": "1", "unit": ""},
                {"name": "oat milk", "qty": "½", "unit": "cup"},
                {"name": "granola", "qty": "¼", "unit": "cup"},
                {"name": "honey", "qty": "1", "unit": "tsp"},
            ],
        },
        "lunch": {"title": "Leftovers: Mini Chicken Tacos", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 12,
            "title": "Teriyaki Salmon Bowl",
            "difficulty": "easy",
            "cuisine": "Japanese",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "prep_time": 25,
            "dietary_tags": ["dairy-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Mix 3 tbsp soy sauce, 2 tbsp mirin, 1 tbsp honey, and 1 tsp grated ginger for the teriyaki glaze.",
                "Pan-fry 4 salmon fillets skin-side down in sesame oil for 4 minutes. Flip, pour glaze over, and cook 3 more minutes until glazed.",
                "Serve over steamed rice with sliced cucumber, edamame, and a sprinkle of sesame seeds.",
            ],
            "ingredients": [
                {"name": "salmon fillets", "qty": "4", "unit": ""},
                {"name": "soy sauce", "qty": "3", "unit": "tbsp"},
                {"name": "mirin", "qty": "2", "unit": "tbsp"},
                {"name": "honey", "qty": "1", "unit": "tbsp"},
                {"name": "fresh ginger, grated", "qty": "1", "unit": "tsp"},
                {"name": "sesame oil", "qty": "1", "unit": "tbsp"},
                {"name": "cucumber", "qty": "1", "unit": ""},
                {"name": "edamame", "qty": "½", "unit": "cup"},
                {"name": "sesame seeds", "qty": "", "unit": "to garnish"},
            ],
        },
    },
    {
        "day": "Sunday",
        "breakfast": {
            "recipe_id": 13,
            "title": "French Toast with Maple Syrup",
            "difficulty": "easy",
            "cuisine": "",
            "url": None,
            "prep_time": 20,
            "dietary_tags": [],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Whisk 3 eggs with ½ cup milk, 1 tsp vanilla, and a pinch of cinnamon in a shallow bowl.",
                "Dip thick-cut bread slices into the egg mixture, letting each side soak for 30 seconds.",
                "Cook in buttered pan over medium heat, 2–3 minutes per side until golden. Serve with maple syrup and berries.",
            ],
            "ingredients": [
                {"name": "thick-cut bread", "qty": "8", "unit": "slices"},
                {"name": "eggs", "qty": "3", "unit": ""},
                {"name": "milk", "qty": "½", "unit": "cup"},
                {"name": "maple syrup", "qty": "4", "unit": "tbsp"},
                {"name": "butter", "qty": "2", "unit": "tbsp"},
                {"name": "cinnamon", "qty": "½", "unit": "tsp"},
                {"name": "vanilla extract", "qty": "1", "unit": "tsp"},
            ],
        },
        "lunch": {"title": "Leftovers: Teriyaki Salmon Bowl", "note": "Pack the night before"},
        "dinner": {
            "recipe_id": 14,
            "title": "Veggie Stir-fry with Tofu",
            "difficulty": "easy",
            "cuisine": "Asian",
            "url": None,
            "prep_time": 25,
            "dietary_tags": ["vegan", "gluten-free"],
            "spice_level": "mild",
            "servings": 4,
            "quick_steps": [
                "Press 400g firm tofu dry, then cut into cubes. Toss in cornstarch, salt, and pepper. Pan-fry in 2 tbsp oil until golden on all sides.",
                "In the same pan, stir-fry broccoli, bell pepper, carrot, and snap peas for 5 minutes over high heat.",
                "Add tofu back, pour over sauce (3 tbsp soy sauce, 1 tbsp sesame oil, 1 tbsp rice vinegar), toss 1 minute. Serve over rice with sesame seeds.",
            ],
            "ingredients": [
                {"name": "firm tofu", "qty": "400", "unit": "g"},
                {"name": "broccoli florets", "qty": "1", "unit": "cup"},
                {"name": "bell pepper, sliced", "qty": "1", "unit": ""},
                {"name": "carrot, julienned", "qty": "1", "unit": ""},
                {"name": "snap peas", "qty": "1", "unit": "cup"},
                {"name": "soy sauce", "qty": "3", "unit": "tbsp"},
                {"name": "sesame oil", "qty": "1", "unit": "tbsp"},
                {"name": "cornstarch", "qty": "2", "unit": "tbsp"},
                {"name": "sesame seeds", "qty": "", "unit": "to garnish"},
            ],
        },
    },
]

SHOPPING = [
    {"ingredient": "salmon fillets", "amounts": "8"},
    {"ingredient": "chicken thighs", "amounts": "500g"},
    {"ingredient": "firm tofu", "amounts": "400g"},
    {"ingredient": "broccoli", "amounts": "3 cups"},
    {"ingredient": "mixed berries", "amounts": "3 cups"},
    {"ingredient": "soy sauce", "amounts": "16 tbsp"},
    {"ingredient": "honey", "amounts": "8 tbsp"},
    {"ingredient": "eggs", "amounts": "11"},
    {"ingredient": "jasmine rice", "amounts": "1.5 cups"},
    {"ingredient": "penne pasta", "amounts": "400g"},
    {"ingredient": "crushed tomatoes", "amounts": "400g"},
    {"ingredient": "heavy cream", "amounts": "½ cup"},
    {"ingredient": "oat milk", "amounts": "1.25 cups"},
    {"ingredient": "granola", "amounts": "¾ cup"},
    {"ingredient": "small flour tortillas", "amounts": "12"},
    {"ingredient": "avocado", "amounts": "1"},
    {"ingredient": "sourdough bread", "amounts": "4 slices"},
    {"ingredient": "sesame oil", "amounts": "5 tsp"},
    {"ingredient": "mirin", "amounts": "2 tbsp"},
    {"ingredient": "edamame", "amounts": "½ cup"},
]

# ---------------------------------------------------------------------------
# Build a minimal MealPlan-like object (no DB needed)
# ---------------------------------------------------------------------------

plan = SimpleNamespace(
    variant="little_ones",
    week_label="2026-W15",
    plan_json=json.dumps(DAYS),
    shopping_json=json.dumps(SHOPPING),
    pdf_data=None,
)

# ---------------------------------------------------------------------------
# Render and write
# ---------------------------------------------------------------------------

OUTPUT = Path(__file__).parent / "preview.pdf"

print("Rendering PDF…")
try:
    pdf_bytes = render_pdf(plan, days=DAYS)
    OUTPUT.write_bytes(pdf_bytes)
    print(f"Done — {len(pdf_bytes) // 1024} KB written to {OUTPUT}")
    print()
    print("Open it with:  xdg-open preview.pdf   (Linux)")
    print("               open preview.pdf        (macOS)")
except Exception as exc:
    print(f"ERROR: {exc}")
    raise

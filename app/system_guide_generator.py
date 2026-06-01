"""System Guide PDF generator — Tier 2 products.

Recipe-focused packs framed around a specific cooking pain point.
Each guide: cover → 1-page intro → 3 recipe cards → shopping list → back cover.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── CONTENT LIBRARY ──────────────────────────────────────────────────────────

SYSTEM_GUIDES: dict[str, dict[str, Any]] = {

    "zero-waste-grocery-audit": {
        "slug": "zero-waste-grocery-audit",
        "guide_title": "Zero-Waste Kitchen",
        "guide_tagline": "Three recipes. One shopping list. Nothing wasted on Friday.",
        "guide_description": "Every perishable ingredient in this pack appears in at least two recipes — by design. Buy once, use completely.",
        "accent_color": "#4a8a5a",
        "includes": ["3 Recipe Cards", "Shopping List", "Waste Map"],

        "intro": {
            "heading": "Why Most Grocery Lists Create Waste",
            "paragraphs": [
                "Standard recipes are written for one dish. You buy a bunch of parsley for Tuesday's chicken. You use four sprigs. The rest sits in the crisper until Friday, when you throw it away and feel guilty.",
                "This pack is built differently. Every fresh ingredient here appears in at least two recipes. One head of garlic. Two lemons. One bunch of parsley. One punnet of cherry tomatoes. Between the three dinners, every item gets fully used.",
                "Cook these in order — Monday, Wednesday, Friday — and you'll end the week with an empty crisper and nothing to throw away.",
            ],
            "prep_box": None,
            "bullets_label": "What makes this pack different",
            "bullets": [
                "Every perishable ingredient is cross-used across at least two recipes",
                "Shopping list is sorted by shelf life — delicate items first, sturdy items last",
                "Quantities are calculated to the gram so you buy exactly what you need",
            ],
        },

        "recipes": [
            {
                "number": "01",
                "name": "Herb-Roasted Chicken Thighs",
                "description": "Golden skin, tender meat, roasted cherry tomatoes that collapse into their own sauce. Uses the first half of your parsley and most of the garlic.",
                "serves": "2",
                "time": "45 min",
                "label": "Cook Monday",
                "ingredients": [
                    "4 chicken thighs, bone-in skin-on",
                    "4 garlic cloves, minced",
                    "½ bunch flat-leaf parsley, roughly chopped",
                    "1 lemon, juice and zest",
                    "250g cherry tomatoes",
                    "2 tbsp olive oil",
                    "Salt and black pepper",
                ],
                "steps": [
                    "Preheat oven to 200°C / 400°F.",
                    "Pat chicken dry. Season generously with salt and pepper.",
                    "Mix garlic, parsley, lemon zest, and olive oil into a rough paste. Rub all over the chicken.",
                    "Arrange chicken skin-side up in a roasting pan. Scatter cherry tomatoes around.",
                    "Roast 35–40 minutes until skin is deep golden and juices run clear.",
                    "Squeeze lemon juice over everything. Rest 5 minutes before serving.",
                ],
                "note": "Save any roasting juices — they make an excellent quick pasta sauce the next day.",
            },
            {
                "number": "02",
                "name": "Pasta al Pomodoro with Herb Crumb",
                "description": "The remaining cherry tomatoes become a sweet, concentrated sauce. Herbed breadcrumbs add texture and use the last of the parsley.",
                "serves": "2",
                "time": "20 min",
                "label": "Cook Wednesday",
                "ingredients": [
                    "200g spaghetti or linguine",
                    "250g cherry tomatoes, halved",
                    "4 garlic cloves, thinly sliced",
                    "½ bunch flat-leaf parsley, roughly chopped",
                    "40g coarse breadcrumbs",
                    "1 lemon, zest only",
                    "4 tbsp olive oil",
                    "Salt and black pepper",
                    "Parmesan to serve",
                ],
                "steps": [
                    "Cook pasta in well-salted boiling water until al dente. Reserve 1 cup pasta water.",
                    "Meanwhile, heat 2 tbsp olive oil over medium heat. Add garlic, cook 1 minute until fragrant.",
                    "Add cherry tomatoes. Cook 8–10 minutes, pressing lightly, until collapsed and jammy.",
                    "In a separate small pan, toast breadcrumbs in 2 tbsp olive oil until golden. Stir in parsley and lemon zest off the heat.",
                    "Toss pasta with tomato sauce, adding pasta water to loosen as needed.",
                    "Serve topped with herb breadcrumbs and parmesan.",
                ],
                "note": "The herb breadcrumb keeps for 2 days in an airtight container.",
            },
            {
                "number": "03",
                "name": "Warm White Bean & Lemon Salad",
                "description": "Creamy white beans with garlic, the last of the lemon, and wilted spinach. On the table in 10 minutes. Uses your final garlic cloves and lemon.",
                "serves": "2",
                "time": "10 min",
                "label": "Cook Friday",
                "ingredients": [
                    "2 × 400g cans white beans, drained and rinsed",
                    "2 garlic cloves, minced",
                    "1 lemon, juice and zest",
                    "Remaining flat-leaf parsley, chopped",
                    "2 large handfuls baby spinach",
                    "3 tbsp olive oil",
                    "Salt and black pepper",
                    "Crusty bread to serve",
                ],
                "steps": [
                    "Warm olive oil in a wide pan over medium heat. Add garlic and cook 1 minute until just golden.",
                    "Add white beans. Stir gently to coat. Warm through for 3–4 minutes.",
                    "Add spinach in handfuls, stirring until just wilted.",
                    "Remove from heat. Add lemon juice, zest, and parsley. Season generously.",
                    "Serve in bowls with crusty bread to soak up the juices.",
                ],
                "note": "This is intentionally simple — let the lemon and garlic do the work.",
            },
        ],

        "shopping": {
            "subhead": "Sorted by shelf life — cook delicate items first.",
            "sections": [
                {
                    "label": "Eat First — Use Monday through Wednesday",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "4 pieces (~800g)", "note": "Recipe 1"},
                        {"item": "Cherry tomatoes", "qty": "500g (1 punnet)", "note": "Recipes 1 + 2"},
                        {"item": "Flat-leaf parsley", "qty": "1 bunch", "note": "Recipes 1, 2 + 3"},
                        {"item": "Baby spinach", "qty": "2 large handfuls", "note": "Recipe 3"},
                    ],
                },
                {
                    "label": "Lasts the Week — Use any day",
                    "items": [
                        {"item": "Garlic", "qty": "1 head (10 cloves)", "note": "All 3 recipes"},
                        {"item": "Lemons", "qty": "2", "note": "Recipes 1, 2 + 3"},
                        {"item": "White beans, canned", "qty": "2 × 400g cans", "note": "Recipe 3"},
                    ],
                },
                {
                    "label": "Pantry",
                    "items": [
                        {"item": "Spaghetti or linguine", "qty": "200g", "note": "Recipe 2"},
                        {"item": "Coarse breadcrumbs", "qty": "40g", "note": "Recipe 2"},
                        {"item": "Parmesan", "qty": "small piece", "note": "Recipe 2"},
                        {"item": "Olive oil", "qty": "good bottle", "note": "All 3 recipes"},
                        {"item": "Salt and black pepper", "qty": "—", "note": "All 3 recipes"},
                        {"item": "Crusty bread", "qty": "1 loaf", "note": "Recipe 3"},
                    ],
                },
            ],
            "note": "Total fresh spend: ~$28–34. Every perishable item above is fully used across the three recipes — nothing left behind on Friday.",
        },
    },

    "cross-over-kitchen": {
        "slug": "cross-over-kitchen",
        "guide_title": "Cross-Over Kitchen",
        "guide_tagline": "Cook once on Sunday. Three completely different meals.",
        "guide_description": "One master protein batch, prepared Sunday. Three distinct cuisines, Monday through Wednesday. Forty minutes less cooking than three separate preps.",
        "accent_color": "#c2522a",
        "includes": ["Master Batch Recipe", "3 Recipe Cards", "Shopping List"],

        "intro": {
            "heading": "One Cook. Three Meals. Zero Repetition.",
            "paragraphs": [
                "The reason meal prep feels like eating the same thing every night: you're prepping finished dishes. Tuesday's chicken looks exactly like Monday's, just colder. By Wednesday you're ordering takeout.",
                "The Cross-Over Kitchen changes the structure. You prep one neutral master batch on Sunday — pulled chicken — and transform it into three completely different meals across the week. Asian on Monday. Mexican on Tuesday. Mediterranean on Wednesday. Same protein, different cuisine, different experience every night.",
            ],
            "prep_box": {
                "label": "Sunday Prep — Do This Once",
                "title": "Pulled Chicken Master Batch",
                "body": "Season 1.2kg bone-in chicken thighs with salt, pepper, garlic powder, smoked paprika. Sear skin-down 4–5 min until golden. Flip, add 240ml chicken stock, cover with foil. Braise at 180°C / 350°F for 45 min. Rest, then pull into shreds and divide into 3 equal portions (~200g each). Refrigerate.",
                "steps": [
                    "Keeps 4 days refrigerated. Use Portion 1 Monday, 2 Tuesday, 3 Wednesday.",
                    "Use bone-in thighs — they stay moist when reheated. Breasts dry out.",
                ],
            },
            "bullets_label": "What's in this pack",
            "bullets": [
                "Recipe 01: Asian Noodle Bowl — soy, sesame, ginger, green onion",
                "Recipe 02: Mexican Taco Plate — cumin, chipotle, avocado, lime",
                "Recipe 03: Mediterranean Grain Bowl — lemon, oregano, feta, olives",
            ],
        },

        "recipes": [
            {
                "number": "01",
                "name": "Asian Noodle Bowl",
                "description": "Chewy soba noodles in a soy-sesame dressing with warm pulled chicken. Ready in 12 minutes — the dressing comes together while the noodles cook.",
                "serves": "2",
                "time": "12 min active",
                "label": "Monday",
                "ingredients": [
                    "1 portion pulled chicken (~200g)",
                    "100g soba or udon noodles",
                    "3 tbsp soy sauce",
                    "1 tbsp sesame oil",
                    "1 tbsp rice vinegar",
                    "1 tsp fresh ginger, grated",
                    "1 garlic clove, minced",
                    "2 green onions, thinly sliced",
                    "1 tsp sesame seeds",
                ],
                "steps": [
                    "Cook noodles per packet instructions. Drain and rinse under cold water.",
                    "Whisk soy sauce, sesame oil, rice vinegar, ginger, and garlic into a dressing.",
                    "Warm pulled chicken in a dry pan over medium heat for 2–3 minutes.",
                    "Toss noodles with dressing until evenly coated.",
                    "Divide into bowls. Top with warm chicken, green onions, and sesame seeds.",
                ],
                "note": "Add a soft-boiled egg or a drizzle of chilli oil if you want more substance.",
            },
            {
                "number": "02",
                "name": "Mexican Taco Plate",
                "description": "Spiced pulled chicken with creamy avocado, fresh cilantro, and a squeeze of lime. Everything comes together in 10 minutes — the chicken does the heavy lifting.",
                "serves": "2",
                "time": "10 min active",
                "label": "Tuesday",
                "ingredients": [
                    "1 portion pulled chicken (~200g)",
                    "4 small corn or flour tortillas",
                    "1 tsp ground cumin",
                    "½ tsp chipotle powder or smoked paprika",
                    "1 lime, halved",
                    "1 ripe avocado, sliced",
                    "Small handful fresh cilantro",
                    "Salsa or 2 diced tomatoes",
                    "Salt to taste",
                ],
                "steps": [
                    "Warm chicken in a pan over medium heat with cumin, chipotle, and a splash of water for 3 minutes, stirring to coat.",
                    "Warm tortillas directly over a gas flame for 20 seconds each side, or in a dry pan.",
                    "Squeeze half the lime over the chicken. Taste and adjust seasoning.",
                    "Assemble: chicken first, then avocado, salsa, and cilantro.",
                    "Serve with remaining lime wedges.",
                ],
                "note": "Smoked paprika works as a chipotle substitute if you prefer a milder heat.",
            },
            {
                "number": "03",
                "name": "Mediterranean Grain Bowl",
                "description": "Fluffy couscous with warm oregano-scented chicken, fresh tomatoes, crumbled feta, and a bright lemon dressing. Fifteen minutes, no shortcuts needed.",
                "serves": "2",
                "time": "15 min active",
                "label": "Wednesday",
                "ingredients": [
                    "1 portion pulled chicken (~200g)",
                    "100g couscous or farro",
                    "1 lemon, juice and zest",
                    "2 tbsp extra virgin olive oil",
                    "1 tsp dried oregano",
                    "Handful cherry tomatoes, halved",
                    "½ cucumber, diced",
                    "40g feta cheese, crumbled",
                    "Small handful kalamata olives",
                ],
                "steps": [
                    "Pour boiling water over couscous (1:1 ratio), cover and rest 5 minutes. Fluff with a fork.",
                    "Warm pulled chicken with oregano and half the lemon juice in a pan for 3 minutes.",
                    "Whisk remaining lemon juice, lemon zest, and olive oil into a dressing.",
                    "Assemble bowls: couscous base, warm chicken, tomatoes, cucumber, feta, and olives.",
                    "Drizzle with dressing. Season with salt and black pepper.",
                ],
                "note": "Farro gives a nuttier texture than couscous — cook it like pasta (20 min in boiling salted water).",
            },
        ],

        "shopping": {
            "subhead": "One master batch, three flavour kits. Buy everything Sunday.",
            "sections": [
                {
                    "label": "Master Batch — Sunday",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "1.2 kg (~6 pieces)", "note": "All 3 meals"},
                        {"item": "Chicken stock", "qty": "240 ml", "note": "Braising liquid"},
                        {"item": "Garlic powder, smoked paprika", "qty": "pantry", "note": "Master batch rub"},
                    ],
                },
                {
                    "label": "Flavour Kit 1 — Asian Noodle Bowl",
                    "items": [
                        {"item": "Soba or udon noodles", "qty": "100g", "note": ""},
                        {"item": "Soy sauce, sesame oil, rice vinegar", "qty": "pantry", "note": ""},
                        {"item": "Fresh ginger", "qty": "small piece", "note": ""},
                        {"item": "Green onions", "qty": "2 stalks", "note": ""},
                        {"item": "Sesame seeds", "qty": "small bag", "note": ""},
                    ],
                },
                {
                    "label": "Flavour Kit 2 — Mexican Taco Plate",
                    "items": [
                        {"item": "Small tortillas (corn or flour)", "qty": "4", "note": ""},
                        {"item": "Cumin, chipotle powder", "qty": "pantry", "note": ""},
                        {"item": "Avocado", "qty": "1 ripe", "note": "Buy day-of if possible"},
                        {"item": "Lime", "qty": "1", "note": ""},
                        {"item": "Fresh cilantro, salsa", "qty": "small amounts", "note": ""},
                    ],
                },
                {
                    "label": "Flavour Kit 3 — Mediterranean Grain Bowl",
                    "items": [
                        {"item": "Couscous or farro", "qty": "100g", "note": ""},
                        {"item": "Lemon", "qty": "1", "note": ""},
                        {"item": "Cherry tomatoes", "qty": "handful", "note": ""},
                        {"item": "Feta cheese", "qty": "40g", "note": ""},
                        {"item": "Kalamata olives", "qty": "small handful", "note": ""},
                        {"item": "Dried oregano", "qty": "pantry", "note": ""},
                    ],
                },
            ],
            "note": "The master batch takes 60 min on Sunday (15 active). Each weeknight meal takes 10–15 min. Total active cooking time for the week: under 60 minutes.",
        },
    },
}


SystemGuideSlug = Enum(  # type: ignore[misc]
    "SystemGuideSlug",
    {k.replace("-", "_"): k for k in SYSTEM_GUIDES},
    type=str,
)


def generate_system_guide_pdf(slug: str) -> bytes:
    """Render a System Guide to a multi-page A4 PDF and return the bytes."""
    if slug not in SYSTEM_GUIDES:
        raise ValueError(
            f"Unknown system guide slug: {slug!r}. "
            f"Available: {list(SYSTEM_GUIDES.keys())}"
        )

    from jinja2 import Environment, FileSystemLoader

    guide = SYSTEM_GUIDES[slug]
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("system_guide.html")
    html = template.render(**guide)

    launch_kwargs: dict = {}
    if ep := os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
        launch_kwargs["executable_path"] = ep

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf_bytes = page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            display_header_footer=False,
        )
        browser.close()

    logger.info("system_guide_generator: rendered %s — %d bytes", slug, len(pdf_bytes))
    return pdf_bytes

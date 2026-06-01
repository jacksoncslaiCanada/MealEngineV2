"""System Guide PDF generator — Tier 2 products.

Each guide is a self-contained PDF: cover + content pages + back cover.
Content is defined as a list of typed blocks (heading, body, checklist,
callout, table, rule, spacer) rendered via system_guide.html.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── CONTENT LIBRARY ──────────────────────────────────────────────────────────

SYSTEM_GUIDES: dict[str, dict[str, Any]] = {

    "zero-waste-grocery-audit": {
        "slug": "zero-waste-grocery-audit",
        "guide_title": "Zero-Waste Grocery Audit",
        "guide_tagline": "Buy exactly what you need. Throw away nothing on Friday.",
        "accent_color": "#4a8a5a",
        "cover_image_url": None,
        "title_size": "34pt",
        "pages": [
            # ── Page 2: The Problem ───────────────────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "Why Your Grocery List Is Costing You $35 a Week"},
                    {"type": "body", "text": "The average household throws away 30–40% of the food they buy. Not because people are careless — because standard recipe lists are written for one dish, not a week. You buy a bunch of cilantro for Tuesday's dinner. You use three sprigs. The rest wilts by Thursday."},
                    {"type": "body", "text": "Multiply that across every fresh herb, leafy green, and half-used aromatics in your cart and the number adds up fast. Most households lose $30–40 per week to produce that dies in the crisper drawer before anyone touches it again."},
                    {"type": "callout", "text": "The problem isn't willpower or organisation. It's that your shopping list was never designed for zero waste."},
                    {"type": "rule"},
                    {"type": "subheading", "text": "Where the Money Goes"},
                    {
                        "type": "table",
                        "label": "Common weekly waste by ingredient category",
                        "headers": ["Category", "Typical waste rate", "Weekly cost lost"],
                        "rows": [
                            ["Fresh herbs (cilantro, parsley, dill)", "70–80%", "$2.50–$3.50"],
                            ["Leafy greens (spinach, kale, arugula)", "40–55%", "$3.00–$4.50"],
                            ["Aromatics (garlic, ginger, shallots)", "35–50%", "$1.50–$2.50"],
                            ["Citrus (lemons, limes)", "45–60%", "$1.80–$2.80"],
                            ["Fresh vegetables (zucchini, peppers)", "30–45%", "$4.00–$6.00"],
                            ["Protein (fish, ground meat)", "15–25%", "$5.00–$9.00"],
                            ["Total estimated weekly loss", "", "$17–$28+"],
                        ],
                    },
                    {"type": "spacer", "size": "sm"},
                    {"type": "body", "text": "The audit framework on the next page eliminates this by designing cross-use into your shopping list before you ever leave the house."},
                ],
            },
            # ── Page 3: The Audit Framework ──────────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "The Three-Step Audit"},
                    {"type": "body", "text": "Run your shopping list through these three steps before you buy anything. The process takes 10 minutes the first time and becomes instinctive within two weeks."},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Step 1 — Map Every Perishable"},
                    {"type": "body", "text": "List every meal you're planning for the week. For each meal, write down every fresh, perishable ingredient it needs. Skip pantry staples (olive oil, dried pasta, canned goods) — focus only on anything that can expire within a week."},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Step 2 — Cross-Reference Appearances"},
                    {"type": "body", "text": "Look for ingredients that appear in more than one meal. These are your anchor ingredients — buy them with confidence. For any ingredient that appears only once, find a substitution that also appears elsewhere in the week, or buy the smallest quantity available."},
                    {"type": "callout", "text": "The goal: every fresh ingredient appears in at least two meals. One appearance = waste risk. Two appearances = justified purchase."},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Step 3 — Tag by Shelf Life"},
                    {"type": "body", "text": "Every fresh ingredient gets one of two tags before it goes on your list:"},
                    {"type": "checklist", "items": [
                        "EAT FIRST — delicate items (fresh fish, leafy greens, fresh herbs, soft fruit) that must be used by Wednesday",
                        "LASTS THE WEEK — sturdy items (root vegetables, citrus, hard cheese, eggs, cabbage) that can hold to Friday or beyond",
                    ]},
                    {"type": "body", "text": "This single habit tells you what to cook on Monday versus Thursday, so nothing sits forgotten at the back of the fridge until it's too late."},
                ],
            },
            # ── Page 4: The One-Pass Shopping List ───────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "The One-Pass Shopping List"},
                    {"type": "body", "text": "Structure your weekly shop by shelf life, not by aisle. This makes priority order obvious when you get home and ensures delicate ingredients get used before they turn."},
                    {"type": "spacer", "size": "sm"},
                    {
                        "type": "table",
                        "label": "EAT FIRST — Cook Monday through Wednesday",
                        "headers": ["Ingredient", "Qty needed", "Used in"],
                        "rows": [
                            ["Fresh fish or seafood", "", ""],
                            ["Leafy greens (spinach, arugula, mixed leaves)", "", ""],
                            ["Fresh herbs (cilantro, basil, dill, parsley)", "", ""],
                            ["Soft fruit (berries, avocado, tomatoes)", "", ""],
                            ["Ground meat", "", ""],
                        ],
                    },
                    {"type": "spacer", "size": "sm"},
                    {
                        "type": "table",
                        "label": "LASTS THE WEEK — Cook Thursday through Sunday",
                        "headers": ["Ingredient", "Qty needed", "Used in"],
                        "rows": [
                            ["Root vegetables (carrots, parsnips, sweet potato)", "", ""],
                            ["Brassicas (broccoli, cabbage, kale)", "", ""],
                            ["Citrus (lemons, limes, oranges)", "", ""],
                            ["Hard cheese (parmesan, feta, aged cheddar)", "", ""],
                            ["Eggs", "", ""],
                        ],
                    },
                    {"type": "spacer", "size": "sm"},
                    {"type": "callout", "text": "Print this page and fill in your weekly ingredients before you shop. The structure becomes automatic within a few uses — you'll stop buying things without a plan for them."},
                ],
            },
            # ── Page 5: The Friday Night Reset ───────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "The Friday Night Reset"},
                    {"type": "body", "text": "Ten minutes on Friday prevents waste, clears mental load, and resets your kitchen for the weekend shop. Do this every week without exception."},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "The Five-Step Reset"},
                    {"type": "checklist", "items": [
                        "Open the fridge and identify everything that needs to be used within 24 hours — move it to eye level on the centre shelf",
                        "Make a quick grain bowl, stir-fry, or frittata with any remaining proteins and vegetables — this is your Friday dinner",
                        "Transfer leftover cooked grains and legumes to a labelled freezer bag — they'll last three months and go straight into next week's meals",
                        "Compost anything genuinely past its prime — don't cook with compromised ingredients; the meal won't be worth it",
                        "Wipe down shelves and reorganise so Sunday's fresh items land in a clean, ordered fridge",
                    ]},
                    {"type": "rule"},
                    {"type": "subheading", "text": "The Compound Effect"},
                    {"type": "body", "text": "A single Friday Reset saves roughly $8–12 that week. Over 52 weeks, that's $400–$600 recovered from produce that would have otherwise gone into the bin."},
                    {"type": "body", "text": "More importantly, a consistently clean fridge eliminates the Sunday dread. You're not starting each week by clearing out last week's failures — you're starting fresh."},
                    {"type": "callout", "text": "Zero waste isn't a personality trait. It's a system. Run the audit before you shop, tag by shelf life, and reset on Friday. That's the whole method."},
                ],
            },
        ],
    },

    "cross-over-kitchen": {
        "slug": "cross-over-kitchen",
        "guide_title": "Cross-Over Kitchen",
        "guide_tagline": "Cook once on Sunday. Eat three completely different meals.",
        "accent_color": "#c2522a",
        "cover_image_url": None,
        "title_size": "38pt",
        "pages": [
            # ── Page 2: The Concept ───────────────────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "One Protein. Three Meals. Zero Repetition."},
                    {"type": "body", "text": "The biggest friction in meal prep isn't the cooking — it's the feeling of eating the same thing every day. Tuesday's chicken looks exactly like Monday's chicken, just colder. By Wednesday, you're ordering takeout."},
                    {"type": "body", "text": "The Cross-Over Kitchen solves this with a single structural change: instead of prepping three separate proteins for three separate meals, you prep one master batch on Sunday and transform it into three completely different flavour profiles across the week."},
                    {"type": "callout", "text": "Same protein. Different cuisine. Different texture. Different experience — every single night."},
                    {"type": "rule"},
                    {"type": "subheading", "text": "Why It Works"},
                    {"type": "checklist", "items": [
                        "One batch cook on Sunday instead of three — cuts active prep time by 40%",
                        "One set of cooking equipment to wash, not three",
                        "The protein absorbs each transformation's flavour — it doesn't taste like 'leftover chicken'",
                        "Smaller shopping list: one protein source, three compact flavour kits",
                    ]},
                    {"type": "spacer", "size": "sm"},
                    {"type": "body", "text": "This guide walks you through the pulled chicken cross-over — the most versatile starting point. Once you have the method, the same logic applies to any protein you cook."},
                ],
            },
            # ── Page 3: The Master Protein ───────────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "Sunday Pulled Chicken — The Master Batch"},
                    {"type": "body", "text": "This is your one Sunday cook. Everything this week comes from this single batch. The seasoning is deliberately neutral so it absorbs each transformation without competing with it."},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Ingredients (serves 3 meals × 2 people)"},
                    {
                        "type": "table",
                        "headers": ["Ingredient", "Quantity", "Note"],
                        "rows": [
                            ["Chicken thighs, bone-in skin-on", "1.2 kg (~6 thighs)", "Thighs stay moist when reheated; breasts dry out"],
                            ["Olive oil", "2 tbsp", ""],
                            ["Kosher salt", "2 tsp", ""],
                            ["Black pepper", "1 tsp", ""],
                            ["Garlic powder", "1 tsp", ""],
                            ["Smoked paprika", "1 tsp", "Adds warmth without committing to a cuisine"],
                            ["Chicken stock", "240 ml", "For braising — keeps the meat moist throughout"],
                        ],
                    },
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Method"},
                    {"type": "checklist", "items": [
                        "Preheat oven to 180°C / 350°F",
                        "Pat chicken dry, rub all over with olive oil, salt, pepper, garlic powder, and paprika",
                        "Sear skin-side down in an oven-safe pan over medium-high heat for 4–5 minutes until deep golden",
                        "Flip, pour stock into the pan, cover tightly with foil",
                        "Braise in oven for 45 minutes until completely tender and pulling away from the bone",
                        "Rest 10 minutes, then remove skin and bones — pull meat into large shreds with two forks",
                        "Divide into three equal portions (~200g each). Refrigerate in separate labelled containers.",
                    ]},
                    {"type": "callout", "text": "Storage: pulled chicken keeps for 4 days refrigerated. Use Portion 1 on Monday, Portion 2 on Tuesday, Portion 3 on Wednesday or Thursday."},
                ],
            },
            # ── Page 4: Transformations 1 & 2 ────────────────────────────
            {
                "blocks": [
                    {"type": "heading", "text": "The Three Transformations"},
                    {"type": "spacer", "size": "sm"},
                    {"type": "subheading", "text": "Transformation 1 — Asian Noodle Bowl (Monday)"},
                    {"type": "body", "text": "Active time: 12 minutes"},
                    {
                        "type": "table",
                        "label": "Flavour kit",
                        "headers": ["Ingredient", "Quantity"],
                        "rows": [
                            ["Soba or udon noodles", "100g dry"],
                            ["Soy sauce", "3 tbsp"],
                            ["Sesame oil", "1 tbsp"],
                            ["Rice vinegar", "1 tbsp"],
                            ["Fresh ginger, grated", "1 tsp"],
                            ["Garlic, minced", "1 clove"],
                            ["Green onions, sliced", "2 stalks"],
                            ["Sesame seeds", "to garnish"],
                        ],
                    },
                    {"type": "body", "text": "Cook noodles per packet. Whisk soy, sesame oil, rice vinegar, ginger, and garlic into a dressing. Warm the pulled chicken in a dry pan for 2–3 minutes. Toss with noodles and dressing. Top with green onions and sesame seeds."},
                    {"type": "rule"},
                    {"type": "subheading", "text": "Transformation 2 — Mexican Taco Plate (Tuesday)"},
                    {"type": "body", "text": "Active time: 10 minutes"},
                    {
                        "type": "table",
                        "label": "Flavour kit",
                        "headers": ["Ingredient", "Quantity"],
                        "rows": [
                            ["Small corn or flour tortillas", "4"],
                            ["Cumin", "1 tsp"],
                            ["Chipotle powder or smoked paprika", "½ tsp"],
                            ["Lime", "1"],
                            ["Avocado", "1"],
                            ["Fresh cilantro", "small handful"],
                            ["Salsa or diced tomato", "to taste"],
                        ],
                    },
                    {"type": "body", "text": "Warm chicken in a pan with cumin, chipotle, and a splash of water for 3 minutes. Warm tortillas. Assemble: chicken, sliced avocado, cilantro, salsa, squeeze of lime."},
                ],
            },
            # ── Page 5: Transformation 3 + Scale-Up Guide ────────────────
            {
                "blocks": [
                    {"type": "subheading", "text": "Transformation 3 — Mediterranean Grain Bowl (Wednesday)"},
                    {"type": "body", "text": "Active time: 15 minutes"},
                    {
                        "type": "table",
                        "label": "Flavour kit",
                        "headers": ["Ingredient", "Quantity"],
                        "rows": [
                            ["Couscous or farro", "100g dry"],
                            ["Lemon", "1"],
                            ["Extra virgin olive oil", "2 tbsp"],
                            ["Dried oregano", "1 tsp"],
                            ["Cherry tomatoes, halved", "handful"],
                            ["Cucumber, diced", "½"],
                            ["Feta cheese, crumbled", "40g"],
                            ["Kalamata olives", "small handful"],
                        ],
                    },
                    {"type": "body", "text": "Cook couscous (5 minutes with boiling water). Warm chicken with oregano and a squeeze of lemon. Assemble: couscous base, chicken, tomatoes, cucumber, feta, olives. Dress with olive oil and remaining lemon juice."},
                    {"type": "rule"},
                    {"type": "heading", "text": "Applying the Method to Any Protein"},
                    {"type": "body", "text": "Pulled chicken is the starting template. Once you understand the structure — neutral master batch, three distinct flavour kits — every protein becomes a cross-over opportunity."},
                    {
                        "type": "table",
                        "headers": ["Base protein", "Transformation 1", "Transformation 2", "Transformation 3"],
                        "rows": [
                            ["Pulled pork shoulder", "Vietnamese rice bowl", "BBQ plate + slaw", "Cuban black bean bowl"],
                            ["Roasted salmon", "Japanese rice bowl + soy", "Niçoise-style salad", "Pasta with capers + dill"],
                            ["Slow-cooked lamb", "Middle Eastern grain bowl", "Greek flatbread wrap", "Moroccan couscous"],
                            ["Roasted chickpeas (vegan)", "Asian noodle bowl", "Taco plate + guacamole", "Mediterranean grain bowl"],
                        ],
                    },
                    {"type": "callout", "text": "Keep the master protein seasoning neutral. Let the flavour kit do the cuisine work. The protein is the canvas — the kit is the painting."},
                ],
            },
        ],
    },
}


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

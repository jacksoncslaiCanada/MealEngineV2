"""System Guide PDF generator — Tier 2 products.

Recipe-focused packs framed around a specific cooking pain point.
Each guide: cover → 1-page intro → 5 recipe cards → shopping list → back cover.
"""
from __future__ import annotations

import copy
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
        "includes": ["5 Recipe Cards", "Shopping List", "Waste Map"],

        "cover_image_prompt": (
            "Professional food photography, bright editorial style. A beautiful flat-lay of a "
            "week's zero-waste meal prep on a white marble countertop — a golden herb-roasted "
            "chicken thigh beside collapsed cherry tomatoes, a bowl of pasta al pomodoro, and a "
            "warm white bean salad with parsley and lemon. A head of garlic, two lemons, a bunch "
            "of flat-leaf parsley, and a punnet of cherry tomatoes are arranged nearby. Crisp "
            "natural window light from the left casting soft shadows. Clean, uncluttered, warm. "
            "Bon Appetit magazine quality."
        ),

        "intro": {
            "heading": "Why Most Grocery Lists Create Waste",
            "highlight": (
                "Standard recipes are written for one dish. You buy a bunch of parsley, use four sprigs, "
                "and throw the rest away on Friday. This pack is built to end that cycle."
            ),
            "paragraphs": [
                "Every fresh ingredient in this guide appears in at least two recipes — by design. One head of garlic. Two lemons. One bunch of parsley. One punnet of cherry tomatoes. Between the five dinners, every perishable item gets fully used.",
                "Cook these in order across the week and you'll end Friday with an empty crisper and nothing to throw away.",
            ],
            "prep_box": None,
            "bullets_label": "What makes this pack different",
            "bullets": [
                "Every perishable ingredient is cross-used across at least two recipes",
                "Shopping list is sorted by shelf life — delicate items first, sturdy items last",
                "Quantities are calculated so you buy exactly what you need",
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
            {
                "number": "04",
                "name": "Green Shakshuka",
                "description": "Eggs poached in a garlicky tomato and spinach sauce. Uses the last of your cherry tomatoes and spinach in one pan, in under 20 minutes.",
                "serves": "2",
                "time": "18 min",
                "label": "Cook Tuesday",
                "ingredients": [
                    "4 large eggs",
                    "250g cherry tomatoes, halved",
                    "2 large handfuls baby spinach",
                    "3 garlic cloves, thinly sliced",
                    "½ tsp ground cumin",
                    "¼ tsp chilli flakes (optional)",
                    "2 tbsp olive oil",
                    "Salt and black pepper",
                    "Crusty bread to serve",
                ],
                "steps": [
                    "Heat olive oil in a wide, lidded pan over medium heat. Add garlic and cook 1 minute until fragrant.",
                    "Add cherry tomatoes, cumin, and chilli flakes. Cook 6–8 minutes until tomatoes are jammy and saucy.",
                    "Stir in spinach and cook until just wilted, about 2 minutes.",
                    "Make 4 wells in the sauce. Crack an egg into each well.",
                    "Cover and cook on low heat for 4–5 minutes until whites are set but yolks are still runny.",
                    "Season and serve directly from the pan with crusty bread.",
                ],
                "note": "A lid is essential — it traps steam and sets the egg whites without overcooking the yolks.",
            },
            {
                "number": "05",
                "name": "Lemon Garlic Pasta with White Beans",
                "description": "A pantry dinner that comes together in 15 minutes. Creamy white beans, bright lemon, and the last of the garlic and parsley make this the easiest recipe in the pack.",
                "serves": "2",
                "time": "15 min",
                "label": "Cook Thursday",
                "ingredients": [
                    "200g spaghetti or pasta of choice",
                    "1 × 400g can white beans, drained and rinsed",
                    "3 garlic cloves, thinly sliced",
                    "1 lemon, juice and zest",
                    "Remaining flat-leaf parsley, chopped",
                    "3 tbsp extra virgin olive oil",
                    "Salt and black pepper",
                    "Parmesan to serve",
                ],
                "steps": [
                    "Cook pasta in well-salted boiling water until al dente. Reserve 1 cup pasta water before draining.",
                    "While pasta cooks, warm olive oil in a wide pan over medium heat. Add garlic, cook 2 minutes until pale golden.",
                    "Add white beans and warm through for 3 minutes, lightly crushing a few with the back of a spoon.",
                    "Add drained pasta to the pan with a splash of pasta water. Toss to combine.",
                    "Remove from heat. Add lemon juice, zest, and most of the parsley. Toss again, adding pasta water to loosen.",
                    "Serve with remaining parsley, parmesan, and a drizzle of olive oil.",
                ],
                "note": "Crushing some of the beans creates a creamy sauce without any cream.",
            },
        ],

        "shopping": {
            "subhead": "Sorted by shelf life — cook delicate items first.",
            "master_sections": [
                {
                    "label": "Fresh & Chilled",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "4 pieces (~800g)"},
                        {"item": "Cherry tomatoes", "qty": "500g"},
                        {"item": "Flat-leaf parsley", "qty": "1 bunch"},
                        {"item": "Baby spinach", "qty": "1 bag (~120g)"},
                        {"item": "Eggs", "qty": "4 large"},
                        {"item": "Lemons", "qty": "2"},
                        {"item": "Garlic", "qty": "1 head"},
                    ],
                },
                {
                    "label": "Pantry & Dry",
                    "items": [
                        {"item": "White beans, canned", "qty": "3 × 400g"},
                        {"item": "Spaghetti or linguine", "qty": "400g"},
                        {"item": "Coarse breadcrumbs", "qty": "40g"},
                        {"item": "Parmesan", "qty": "small piece"},
                        {"item": "Crusty bread", "qty": "1 loaf"},
                        {"item": "Olive oil", "qty": "good bottle"},
                        {"item": "Ground cumin, chilli flakes", "qty": "pantry"},
                        {"item": "Salt and black pepper", "qty": "pantry"},
                    ],
                },
            ],
            "sections": [
                {
                    "label": "Eat First — Use Monday through Wednesday",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "4 pieces (~800g)", "note": "Recipe 1"},
                        {"item": "Cherry tomatoes", "qty": "500g (1 punnet)", "note": "Recipes 1, 2 + 4"},
                        {"item": "Flat-leaf parsley", "qty": "1 bunch", "note": "Recipes 1, 2, 3 + 5"},
                        {"item": "Baby spinach", "qty": "1 bag (~120g)", "note": "Recipes 3 + 4"},
                        {"item": "Eggs", "qty": "4 large", "note": "Recipe 4"},
                    ],
                },
                {
                    "label": "Lasts the Week — Use any day",
                    "items": [
                        {"item": "Garlic", "qty": "1 head (12+ cloves)", "note": "All 5 recipes"},
                        {"item": "Lemons", "qty": "2", "note": "Recipes 1, 2, 3 + 5"},
                        {"item": "White beans, canned", "qty": "3 × 400g cans", "note": "Recipes 3 + 5"},
                    ],
                },
                {
                    "label": "Pantry",
                    "items": [
                        {"item": "Spaghetti or linguine", "qty": "400g total", "note": "Recipes 2 + 5"},
                        {"item": "Coarse breadcrumbs", "qty": "40g", "note": "Recipe 2"},
                        {"item": "Parmesan", "qty": "small piece", "note": "Recipes 2 + 5"},
                        {"item": "Ground cumin, chilli flakes", "qty": "pantry", "note": "Recipe 4"},
                        {"item": "Olive oil", "qty": "good bottle", "note": "All 5 recipes"},
                        {"item": "Salt and black pepper", "qty": "—", "note": "All 5 recipes"},
                        {"item": "Crusty bread", "qty": "1 loaf", "note": "Recipes 3 + 4"},
                    ],
                },
            ],
            "note": "Total fresh spend: ~$32–40. Every perishable item above is shared across at least two recipes — nothing left behind on Friday.",
        },
    },

    "cross-over-kitchen": {
        "slug": "cross-over-kitchen",
        "guide_title": "Cross-Over Kitchen",
        "guide_tagline": "Cook once on Sunday. Three completely different meals.",
        "guide_description": "One master protein batch, prepared Sunday. Three distinct cuisines, Monday through Wednesday. Forty minutes less cooking than three separate preps.",
        "accent_color": "#c2522a",
        "includes": ["Master Batch Recipe", "5 Recipe Cards", "Shopping List"],

        "cover_image_prompt": (
            "Professional food photography, bright editorial style. Five small bowls arranged on "
            "a white marble countertop, each showing a different cuisine — an Asian noodle bowl "
            "with sesame and green onion, a Mexican taco plate with avocado, a Mediterranean "
            "grain bowl with feta and olives, Thai fried rice with a fried egg, and a rustic "
            "white bean chicken soup. In the centre, a pile of tender pulled chicken. Crisp "
            "natural window light from the left. Vibrant, clean, editorial. "
            "Bon Appetit magazine quality."
        ),

        "intro": {
            "heading": "One Cook. Five Meals. Zero Repetition.",
            "highlight": (
                "Most meal prep fails because you're prepping finished dishes. Tuesday's chicken "
                "looks exactly like Monday's, just colder. This guide preps one thing — and turns it "
                "into five completely different meals."
            ),
            "paragraphs": [
                "Sunday: one neutral master batch of pulled chicken, 60 minutes, 15 active. Monday through Friday: five different cuisines — Asian, Mexican, Mediterranean, Thai, and a comforting soup. Same protein, completely different experience every night.",
            ],
            "prep_box": {
                "label": "Sunday Prep — Do This Once",
                "title": "Pulled Chicken Master Batch",
                "body": "Season 1.8kg bone-in chicken thighs with salt, pepper, garlic powder, smoked paprika. Sear skin-down 4–5 min until golden. Flip, add 300ml chicken stock, cover with foil. Braise at 180°C / 350°F for 45 min. Rest, then pull into shreds and divide into 5 equal portions (~160g each). Refrigerate.",
                "steps": [
                    "Keeps 4 days refrigerated. Use Portions 1–3 Mon–Wed, Portions 4–5 Thu–Fri.",
                    "Use bone-in thighs — they stay moist when reheated. Breasts dry out.",
                ],
            },
            "bullets_label": "What's in this pack",
            "bullets": [
                "Recipe 01: Asian Noodle Bowl — soy, sesame, ginger, green onion",
                "Recipe 02: Mexican Taco Plate — cumin, chipotle, avocado, lime",
                "Recipe 03: Mediterranean Grain Bowl — lemon, oregano, feta, olives",
                "Recipe 04: Thai Fried Rice — fish sauce, lime, egg, chilli",
                "Recipe 05: Chicken & White Bean Soup — garlic, spinach, stock",
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
            {
                "number": "04",
                "name": "Thai Fried Rice",
                "description": "Day-old rice, a fried egg on top, and the pulled chicken transformed with fish sauce, lime, and chilli. One of the fastest meals in the pack.",
                "serves": "2",
                "time": "12 min active",
                "label": "Thursday",
                "ingredients": [
                    "1 portion pulled chicken (~160g)",
                    "300g cooked jasmine rice (day-old is best)",
                    "2 eggs",
                    "2 tbsp fish sauce",
                    "1 tbsp soy sauce",
                    "1 tsp sugar",
                    "1 lime, halved",
                    "2 garlic cloves, minced",
                    "2 green onions, sliced",
                    "1 red chilli, sliced (optional)",
                    "2 tbsp neutral oil",
                ],
                "steps": [
                    "Mix fish sauce, soy sauce, and sugar in a small bowl. Set aside.",
                    "Heat 1 tbsp oil in a wok or large pan over high heat until smoking. Add garlic, stir 30 seconds.",
                    "Add cold rice, breaking up any clumps. Stir-fry 3 minutes until starting to crisp.",
                    "Add pulled chicken and sauce mixture. Toss well for 2 minutes.",
                    "Push rice to one side. Add remaining oil, crack in eggs, and scramble briefly before folding through the rice.",
                    "Serve topped with green onions, chilli, and a squeeze of lime.",
                ],
                "note": "Day-old rice fries better than fresh — the drier grains separate and crisp properly.",
            },
            {
                "number": "05",
                "name": "Chicken & White Bean Soup",
                "description": "A quietly comforting Friday soup. The pulled chicken melts into the broth with white beans, garlic, and spinach — on the table in 20 minutes.",
                "serves": "2",
                "time": "20 min",
                "label": "Friday",
                "ingredients": [
                    "1 portion pulled chicken (~160g)",
                    "1 × 400g can white beans, drained and rinsed",
                    "3 garlic cloves, minced",
                    "500ml chicken stock",
                    "2 large handfuls baby spinach",
                    "1 lemon, juice only",
                    "2 tbsp olive oil",
                    "Salt and black pepper",
                    "Crusty bread to serve",
                ],
                "steps": [
                    "Warm olive oil in a medium saucepan over medium heat. Add garlic and cook 2 minutes until softened.",
                    "Add chicken stock and bring to a gentle simmer.",
                    "Add white beans and pulled chicken. Simmer 8–10 minutes until warmed through and slightly thickened.",
                    "Lightly crush a few beans against the side of the pot to thicken the broth.",
                    "Stir in spinach and cook until just wilted, about 1 minute.",
                    "Add lemon juice. Taste and season. Serve with crusty bread.",
                ],
                "note": "This is intentionally simple. The pulled chicken carries enough flavour — don't over-season.",
            },
        ],

        "shopping": {
            "subhead": "One master batch, five flavour kits. Buy everything Sunday.",
            "master_sections": [
                {
                    "label": "Protein",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "1.8 kg (~8 pcs)"},
                    ],
                },
                {
                    "label": "Fresh & Chilled",
                    "items": [
                        {"item": "Eggs", "qty": "2 large"},
                        {"item": "Fresh ginger", "qty": "small piece"},
                        {"item": "Green onions", "qty": "4 stalks"},
                        {"item": "Avocado", "qty": "1 ripe"},
                        {"item": "Lime", "qty": "3"},
                        {"item": "Fresh cilantro", "qty": "small bunch"},
                        {"item": "Cherry tomatoes", "qty": "handful"},
                        {"item": "Baby spinach", "qty": "2 large handfuls"},
                        {"item": "Lemon", "qty": "2"},
                        {"item": "Red chilli (optional)", "qty": "1"},
                        {"item": "Feta cheese", "qty": "40g"},
                    ],
                },
                {
                    "label": "Pantry & Dry",
                    "items": [
                        {"item": "Chicken stock", "qty": "800 ml total"},
                        {"item": "Soba or udon noodles", "qty": "100g"},
                        {"item": "Small tortillas (corn or flour)", "qty": "4"},
                        {"item": "Couscous or farro", "qty": "100g"},
                        {"item": "Jasmine rice (cook Sunday)", "qty": "150g dry"},
                        {"item": "White beans, canned", "qty": "1 × 400g"},
                        {"item": "Kalamata olives", "qty": "small handful"},
                        {"item": "Salsa", "qty": "small jar"},
                        {"item": "Crusty bread", "qty": "1 loaf"},
                    ],
                },
                {
                    "label": "Condiments & Spices",
                    "items": [
                        {"item": "Soy sauce, sesame oil, rice vinegar", "qty": "pantry"},
                        {"item": "Sesame seeds", "qty": "small bag"},
                        {"item": "Cumin, chipotle or smoked paprika", "qty": "pantry"},
                        {"item": "Dried oregano", "qty": "pantry"},
                        {"item": "Fish sauce", "qty": "pantry"},
                        {"item": "Garlic powder, smoked paprika", "qty": "pantry"},
                        {"item": "Olive oil, neutral oil", "qty": "pantry"},
                    ],
                },
            ],
            "sections": [
                {
                    "label": "Master Batch — Sunday",
                    "items": [
                        {"item": "Chicken thighs, bone-in skin-on", "qty": "1.8 kg (~8 pieces)", "note": "All 5 meals"},
                        {"item": "Chicken stock", "qty": "300 ml", "note": "Braising liquid"},
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
                {
                    "label": "Flavour Kit 4 — Thai Fried Rice",
                    "items": [
                        {"item": "Jasmine rice (cook Sunday, refrigerate)", "qty": "150g dry", "note": "Day-old is best"},
                        {"item": "Eggs", "qty": "2 large", "note": ""},
                        {"item": "Fish sauce, soy sauce", "qty": "pantry", "note": ""},
                        {"item": "Lime", "qty": "1", "note": ""},
                        {"item": "Red chilli (optional)", "qty": "1", "note": ""},
                    ],
                },
                {
                    "label": "Flavour Kit 5 — Chicken & White Bean Soup",
                    "items": [
                        {"item": "White beans, canned", "qty": "1 × 400g can", "note": ""},
                        {"item": "Chicken stock", "qty": "500 ml", "note": ""},
                        {"item": "Baby spinach", "qty": "2 large handfuls", "note": ""},
                        {"item": "Lemon", "qty": "1", "note": ""},
                        {"item": "Crusty bread", "qty": "1 loaf", "note": ""},
                    ],
                },
            ],
            "note": "The master batch takes 60 min on Sunday (15 active). Each weeknight meal takes 10–20 min. Total active cooking time for the week: under 75 minutes.",
        },
    },
}


SystemGuideSlug = Enum(  # type: ignore[misc]
    "SystemGuideSlug",
    {k.replace("-", "_"): k for k in SYSTEM_GUIDES},
    type=str,
)


def generate_system_guide_pdf(slug: str, *, cover_image_url: str | None = None) -> bytes:
    """Render a System Guide to a multi-page A4 PDF and return the bytes."""
    if slug not in SYSTEM_GUIDES:
        raise ValueError(
            f"Unknown system guide slug: {slug!r}. "
            f"Available: {list(SYSTEM_GUIDES.keys())}"
        )

    from jinja2 import Environment, FileSystemLoader

    # Compute cover image URL from predictable Supabase path if not supplied
    base_img_url = ""
    try:
        from app.config import settings
        if settings.supabase_url and settings.supabase_images_bucket:
            base_img_url = (
                f"{settings.supabase_url}/storage/v1/object/public/"
                f"{settings.supabase_images_bucket}/cover-images"
            )
    except Exception:
        pass

    if cover_image_url is None:
        cover_image_url = f"{base_img_url}/system-guide-{slug}.webp" if base_img_url else ""

    # Deep-copy so we never mutate the module-level SYSTEM_GUIDES constant
    guide_data = copy.deepcopy(SYSTEM_GUIDES[slug])

    # Auto-populate recipe image URLs (empty string = placeholder shown until cron runs)
    if base_img_url:
        for i, recipe in enumerate(guide_data["recipes"], 1):
            if not recipe.get("image_url"):
                recipe["image_url"] = f"{base_img_url}/system-guide-{slug}-recipe-{i:02d}.webp"

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("system_guide.html")
    html = template.render(**guide_data, cover_image_url=cover_image_url or "")

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

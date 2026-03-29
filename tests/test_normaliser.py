"""Unit tests for app/normaliser.py — normalise_ingredient()."""
from __future__ import annotations

import pytest

from app.normaliser import normalise_ingredient


@pytest.mark.parametrize("raw, expected", [
    # Lower-case pass-through
    ("olive oil", "olive oil"),
    ("salt", "salt"),

    # Prep prefix stripping
    ("diced onion", "onion"),
    ("finely diced onion", "onion"),
    ("freshly ground black pepper", "black pepper"),
    ("chopped garlic", "garlic"),
    ("minced garlic", "garlic"),
    ("grated parmesan", "parmesan"),
    ("frozen peas", "peas"),  # plain -s not stripped by design
    ("cooked rice", "rice"),

    # Trailing word stripping
    ("garlic cloves", "garlic"),
    ("chicken thighs", "chicken"),
    ("chicken breast", "chicken"),
    ("chicken wings", "chicken"),
    ("salmon fillets", "salmon"),
    ("lemon zest", "lemon"),
    ("lemon juice", "lemon"),
    ("parsley leaves", "parsley"),
    ("basil leaves", "basil"),

    # Both prefix and trailing
    ("boneless skinless chicken thighs", "chicken"),
    ("fresh parsley leaves", "parsley"),

    # Parenthetical removal
    ("butter (unsalted)", "butter"),
    ("milk (full fat)", "milk"),

    # Synonym map
    ("bell pepper", "pepper"),
    ("capsicum", "pepper"),
    ("cilantro", "coriander"),
    ("chilli", "chili"),
    ("chilli pepper", "chili"),
    ("cornflour", "cornstarch"),
    ("corn flour", "cornstarch"),
    ("bicarbonate of soda", "baking soda"),
    ("double cream", "heavy cream"),
    ("plain flour", "flour"),
    ("all-purpose flour", "flour"),
    ("chicken broth", "chicken stock"),
    ("vegetable broth", "vegetable stock"),
    ("spring onion", "scallion"),
    ("green onion", "scallion"),
    ("cherry tomato", "tomato"),
    ("passata", "tomato puree"),
    ("greek yogurt", "yogurt"),
    ("greek yoghurt", "yogurt"),
    ("natural yoghurt", "yogurt"),
    ("vegetable oil", "oil"),
    ("sunflower oil", "oil"),
    ("garbanzo bean", "chickpeas"),
    ("garbanzo", "chickpeas"),

    # Pluralisation
    ("berries", "berry"),

    # Extra-virgin synonym (synonym checked after prefix strip)
    ("extra-virgin olive oil", "olive oil"),

    # Case normalisation
    ("Chicken Thighs", "chicken"),
    ("GARLIC CLOVES", "garlic"),
    ("Fresh Basil", "basil"),
])
def test_normalise_ingredient(raw, expected):
    assert normalise_ingredient(raw) == expected


def test_empty_parens_leave_word():
    # "(optional)" stripped but core word kept
    result = normalise_ingredient("chili flakes (optional)")
    assert result == "chili"


def test_unknown_ingredient_returned_as_is():
    result = normalise_ingredient("quinoa")
    assert result == "quinoa"


def test_single_word_no_change():
    assert normalise_ingredient("butter") == "butter"


def test_whitespace_collapsed():
    assert normalise_ingredient("  olive   oil  ") == "olive oil"

"""Accuracy test for the ingredient extractor against ground truth.

Uses the 15-meal ground truth fixture in tests/fixtures/ground_truth_ingredients.json.
Requires a real ANTHROPIC_API_KEY — the test is skipped if the key is absent or empty.

Run manually:
    ANTHROPIC_API_KEY=sk-ant-... pytest tests/test_extractor_accuracy.py -v -s
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Ingredient, RawRecipe
from app.extractor import extract_ingredients

# ---------------------------------------------------------------------------
# Fixture path
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ground_truth_ingredients.json"

# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------

def _normalise(name: str) -> str:
    return name.strip().lower()


def _names_match(extracted: str, expected: str) -> bool:
    """True if the two ingredient names are considered the same.

    Accepts exact match OR one being a substring of the other (handles
    minor phrasing differences like "chicken thigh" vs "chicken thighs").
    """
    a = _normalise(extracted)
    b = _normalise(expected)
    return a == b or a in b or b in a


def _recall(extracted_names: list[str], expected_names: list[str]) -> float:
    """Fraction of expected ingredients found in the extracted list."""
    if not expected_names:
        return 1.0
    matched = sum(
        1 for exp in expected_names
        if any(_names_match(ext, exp) for ext in extracted_names)
    )
    return matched / len(expected_names)


# ---------------------------------------------------------------------------
# Pytest skip condition
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

requires_api_key = pytest.mark.skipif(
    not API_KEY,
    reason="ANTHROPIC_API_KEY not set — skipping live Claude accuracy test",
)

# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ground_truth_fixture_loaded():
    """Sanity-check the fixture file exists and has 15 entries."""
    data = json.loads(FIXTURE_PATH.read_text())
    assert len(data) == 15, f"Expected 15 meals, got {len(data)}"
    for entry in data:
        assert "meal_id" in entry
        assert "raw_content" in entry
        assert "expected_ingredients" in entry
        assert len(entry["expected_ingredients"]) > 0, (
            f"Meal {entry['meal_id']} has no expected ingredients"
        )


@requires_api_key
def test_extractor_accuracy_against_ground_truth(db):
    """Extract ingredients from all 15 ground-truth recipes and assert ≥90% recall.

    Each recipe is processed independently. We report per-recipe recall and the
    overall recall across all 155 expected ingredients.
    """
    data = json.loads(FIXTURE_PATH.read_text())
    client = anthropic.Anthropic(api_key=API_KEY)

    _recipe_counter = 0

    total_expected = 0
    total_matched = 0
    failing_meals: list[str] = []

    for entry in data:
        _recipe_counter += 1
        # Insert a RawRecipe with the fixture's raw_content
        recipe = RawRecipe(
            source="themealdb",
            source_id=f"gt_acc_{_recipe_counter:03d}",
            raw_content=entry["raw_content"],
            url=f"https://www.themealdb.com/meal/{entry['meal_id']}",
            fetched_at=datetime.now(timezone.utc),
        )
        db.add(recipe)
        db.flush()

        rows = extract_ingredients(db, recipe, client=client)

        extracted_names = [r.ingredient_name for r in rows]
        expected_names = [i["ingredient_name"] for i in entry["expected_ingredients"]]

        recall = _recall(extracted_names, expected_names)
        total_expected += len(expected_names)
        matched = round(recall * len(expected_names))
        total_matched += matched

        print(
            f"  {entry['meal_name']:35s}  "
            f"extracted={len(extracted_names):2d}  "
            f"expected={len(expected_names):2d}  "
            f"recall={recall:.0%}"
        )

        if recall < 0.90:
            failing_meals.append(
                f"{entry['meal_name']}: recall={recall:.1%} "
                f"(missing: {[e for e in expected_names if not any(_names_match(x, e) for x in extracted_names)]})"
            )

    overall_recall = total_matched / total_expected if total_expected else 0.0
    print(f"\n  Overall recall: {total_matched}/{total_expected} = {overall_recall:.1%}")

    assert overall_recall >= 0.90, (
        f"Overall recall {overall_recall:.1%} is below 90%.\n"
        f"Per-recipe failures:\n" + "\n".join(f"  - {m}" for m in failing_meals)
    )


@requires_api_key
def test_extractor_deduplication_live(db):
    """Calling extract_ingredients twice on the same recipe makes only 1 API call."""
    data = json.loads(FIXTURE_PATH.read_text())
    entry = data[0]  # Teriyaki Chicken Casserole

    recipe = RawRecipe(
        source="themealdb",
        source_id="gt_dedup_001",
        raw_content=entry["raw_content"],
        url="https://www.themealdb.com/meal/dedup",
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(recipe)
    db.flush()

    client = anthropic.Anthropic(api_key=API_KEY)
    first_run = extract_ingredients(db, recipe, client=client)
    second_run = extract_ingredients(db, recipe, client=client)

    assert len(first_run) > 0, "First run should extract ingredients"
    assert second_run == [], "Second run should be skipped (deduplication)"

    # Only 1 row per ingredient — no doubles in DB
    db_rows = db.query(Ingredient).filter(Ingredient.recipe_id == recipe.id).all()
    assert len(db_rows) == len(first_run)

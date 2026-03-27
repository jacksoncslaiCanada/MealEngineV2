"""Unit tests for app/extractor.py.

All tests use an in-memory SQLite database and a mocked Anthropic client so
no real API calls are made.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Ingredient, RawRecipe, Source
from app.extractor import extract_ingredients, extract_all_unprocessed

_recipe_counter = 0


# ---------------------------------------------------------------------------
# Helpers / fixtures
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


def _make_source(db, platform="themealdb", handle="themealdb_public") -> Source:
    source = Source(
        platform=platform,
        handle=handle,
        display_name="TheMealDB",
        status="active",
        added_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.flush()
    return source


def _make_recipe(db, source_fk: int | None = None, raw_content: str = "2 cups flour, 1 egg") -> RawRecipe:
    global _recipe_counter
    _recipe_counter += 1
    recipe = RawRecipe(
        source="themealdb",
        source_id=f"test_meal_{_recipe_counter:04d}",
        raw_content=raw_content,
        url=f"https://www.themealdb.com/meal/{_recipe_counter}",
        fetched_at=datetime.now(timezone.utc),
        source_fk=source_fk,
    )
    db.add(recipe)
    db.flush()
    return recipe


def _make_tool_use_block(ingredients: list[dict]) -> MagicMock:
    """Build a mock content block that looks like a tool_use response."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "record_ingredients"
    block.input = {"ingredients": ingredients}
    return block


def _make_anthropic_response(ingredients: list[dict]) -> MagicMock:
    """Return a mock anthropic response with a single tool_use block."""
    resp = MagicMock()
    resp.content = [_make_tool_use_block(ingredients)]
    return resp


def _make_client(ingredients: list[dict]) -> MagicMock:
    """Return a mock Anthropic client that returns the given ingredients."""
    client = MagicMock()
    client.messages.create.return_value = _make_anthropic_response(ingredients)
    return client


# ---------------------------------------------------------------------------
# extract_ingredients — basic behaviour
# ---------------------------------------------------------------------------

def test_extract_creates_ingredient_rows(db):
    source = _make_source(db)
    recipe = _make_recipe(db, source_fk=source.id)
    client = _make_client([
        {"ingredient_name": "flour", "quantity": "2", "unit": "cup"},
        {"ingredient_name": "egg", "quantity": "1", "unit": None},
    ])

    rows = extract_ingredients(db, recipe, client=client)

    assert len(rows) == 2
    names = {r.ingredient_name for r in rows}
    assert names == {"flour", "egg"}


def test_extract_persists_to_db(db):
    source = _make_source(db)
    recipe = _make_recipe(db, source_fk=source.id)
    client = _make_client([
        {"ingredient_name": "olive oil", "quantity": "2", "unit": "tbsp"},
    ])

    extract_ingredients(db, recipe, client=client)

    saved = db.query(Ingredient).filter(Ingredient.recipe_id == recipe.id).all()
    assert len(saved) == 1
    assert saved[0].ingredient_name == "olive oil"
    assert saved[0].quantity == "2"
    assert saved[0].unit == "tbsp"


def test_extract_sets_recipe_id_fk(db):
    source = _make_source(db)
    recipe = _make_recipe(db, source_fk=source.id)
    client = _make_client([{"ingredient_name": "salt", "quantity": None, "unit": None}])

    rows = extract_ingredients(db, recipe, client=client)

    assert rows[0].recipe_id == recipe.id


def test_extract_sets_source_id_fk(db):
    source = _make_source(db)
    recipe = _make_recipe(db, source_fk=source.id)
    client = _make_client([{"ingredient_name": "pepper", "quantity": "1", "unit": "tsp"}])

    rows = extract_ingredients(db, recipe, client=client)

    assert rows[0].source_id == source.id


def test_extract_source_id_null_when_no_source_fk(db):
    recipe = _make_recipe(db, source_fk=None)
    client = _make_client([{"ingredient_name": "water", "quantity": "1", "unit": "cup"}])

    rows = extract_ingredients(db, recipe, client=client)

    assert rows[0].source_id is None


def test_extract_sets_extracted_at(db):
    recipe = _make_recipe(db)
    client = _make_client([{"ingredient_name": "butter", "quantity": "50", "unit": "g"}])

    rows = extract_ingredients(db, recipe, client=client)

    assert rows[0].extracted_at is not None


def test_extract_null_quantity_and_unit_allowed(db):
    recipe = _make_recipe(db)
    client = _make_client([
        {"ingredient_name": "garlic", "quantity": None, "unit": None},
    ])

    rows = extract_ingredients(db, recipe, client=client)

    assert rows[0].quantity is None
    assert rows[0].unit is None


# ---------------------------------------------------------------------------
# extract_ingredients — deduplication
# ---------------------------------------------------------------------------

def test_extract_skips_already_processed_recipe(db):
    recipe = _make_recipe(db)
    # Pre-seed an ingredient row for this recipe
    existing = Ingredient(
        ingredient_name="onion",
        recipe_id=recipe.id,
        extracted_at=datetime.now(timezone.utc),
    )
    db.add(existing)
    db.commit()

    client = _make_client([{"ingredient_name": "garlic", "quantity": None, "unit": None}])
    rows = extract_ingredients(db, recipe, client=client)

    # Should return empty — Claude was never called
    assert rows == []
    client.messages.create.assert_not_called()


def test_extract_returns_empty_list_on_skip(db):
    recipe = _make_recipe(db)
    db.add(Ingredient(
        ingredient_name="tomato",
        recipe_id=recipe.id,
        extracted_at=datetime.now(timezone.utc),
    ))
    db.commit()

    client = MagicMock()
    result = extract_ingredients(db, recipe, client=client)
    assert result == []


# ---------------------------------------------------------------------------
# extract_ingredients — Claude API call parameters
# ---------------------------------------------------------------------------

def test_extract_calls_correct_model(db):
    recipe = _make_recipe(db)
    client = _make_client([{"ingredient_name": "milk", "quantity": "1", "unit": "cup"}])

    extract_ingredients(db, recipe, client=client)

    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-opus-4-6"


def test_extract_uses_adaptive_thinking(db):
    recipe = _make_recipe(db)
    client = _make_client([{"ingredient_name": "sugar", "quantity": "2", "unit": "tbsp"}])

    extract_ingredients(db, recipe, client=client)

    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["thinking"] == {"type": "adaptive"}


def test_extract_forces_tool_choice(db):
    recipe = _make_recipe(db)
    client = _make_client([{"ingredient_name": "vanilla", "quantity": "1", "unit": "tsp"}])

    extract_ingredients(db, recipe, client=client)

    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "record_ingredients"}


def test_extract_includes_raw_content_in_prompt(db):
    recipe = _make_recipe(db, raw_content="Special raw content here")
    client = _make_client([{"ingredient_name": "oil", "quantity": None, "unit": None}])

    extract_ingredients(db, recipe, client=client)

    call_kwargs = client.messages.create.call_args[1]
    messages = call_kwargs["messages"]
    assert any("Special raw content here" in str(m) for m in messages)


# ---------------------------------------------------------------------------
# extract_all_unprocessed
# ---------------------------------------------------------------------------

def test_extract_all_processes_unprocessed_recipes(db):
    source = _make_source(db)
    _make_recipe(db, source_fk=source.id, raw_content="1 cup rice")
    _make_recipe(db, source_fk=source.id, raw_content="2 eggs")
    db.commit()

    client = MagicMock()
    client.messages.create.side_effect = [
        _make_anthropic_response([{"ingredient_name": "rice", "quantity": "1", "unit": "cup"}]),
        _make_anthropic_response([{"ingredient_name": "egg", "quantity": "2", "unit": None}]),
    ]

    rows = extract_all_unprocessed(db, client=client)

    assert len(rows) == 2
    names = {r.ingredient_name for r in rows}
    assert names == {"rice", "egg"}


def test_extract_all_skips_already_processed(db):
    r1 = _make_recipe(db, raw_content="1 cup milk")
    r2 = _make_recipe(db, raw_content="3 cloves garlic")
    # r1 already processed
    db.add(Ingredient(
        ingredient_name="milk",
        recipe_id=r1.id,
        extracted_at=datetime.now(timezone.utc),
    ))
    db.commit()

    client = _make_client([{"ingredient_name": "garlic", "quantity": "3", "unit": "clove"}])

    rows = extract_all_unprocessed(db, client=client)

    assert len(rows) == 1
    assert rows[0].ingredient_name == "garlic"
    # Claude called only once (for r2)
    assert client.messages.create.call_count == 1


def test_extract_all_respects_limit(db):
    for i in range(5):
        _make_recipe(db, raw_content=f"ingredient {i}")

    client = _make_client([{"ingredient_name": "item", "quantity": None, "unit": None}])
    # Patch to handle multiple calls
    client.messages.create.side_effect = [
        _make_anthropic_response([{"ingredient_name": f"item_{i}", "quantity": None, "unit": None}])
        for i in range(3)
    ]

    rows = extract_all_unprocessed(db, client=client, limit=3)

    assert client.messages.create.call_count == 3
    assert len(rows) == 3


def test_extract_all_returns_empty_when_all_processed(db):
    recipe = _make_recipe(db)
    db.add(Ingredient(
        ingredient_name="flour",
        recipe_id=recipe.id,
        extracted_at=datetime.now(timezone.utc),
    ))
    db.commit()

    client = MagicMock()
    rows = extract_all_unprocessed(db, client=client)

    assert rows == []
    client.messages.create.assert_not_called()


def test_extract_all_empty_db(db):
    client = MagicMock()
    rows = extract_all_unprocessed(db, client=client)
    assert rows == []
    client.messages.create.assert_not_called()

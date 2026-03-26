"""Unit tests for the TheMealDB connector."""

from datetime import datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe, Source
from app.connectors.themealdb import fetch_themealdb_recipes, save_themealdb_recipes


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_meal(
    meal_id: str = "52772",
    name: str = "Test Chicken",
    category: str = "Chicken",
    area: str = "Japanese",
    instructions: str = "Cook everything together and serve.",
    ingredients: dict | None = None,
) -> dict:
    meal = {
        "idMeal": meal_id,
        "strMeal": name,
        "strCategory": category,
        "strArea": area,
        "strInstructions": instructions,
        "strMealThumb": f"https://www.themealdb.com/images/media/meals/test.jpg",
        "strTags": None,
        "strYoutube": "",
        "strSource": None,
        "strImageSource": None,
        "strCreativeCommonsConfirmed": None,
        "dateModified": None,
        "strDrinkAlternate": None,
    }
    # Populate ingredient/measure slots (20 max)
    ing = ingredients if ingredients is not None else {"soy sauce": "3/4 cup", "chicken": "500g"}
    keys = list(ing.items())
    for i in range(1, 21):
        if i <= len(keys):
            meal[f"strIngredient{i}"] = keys[i - 1][0]
            meal[f"strMeasure{i}"] = keys[i - 1][1]
        else:
            meal[f"strIngredient{i}"] = ""
            meal[f"strMeasure{i}"] = ""
    return meal


def _make_response(meals: list[dict] | None) -> httpx.Response:
    return httpx.Response(200, json={"meals": meals})


def _make_client(responses: list[httpx.Response]) -> httpx.Client:
    """Return an httpx.Client that replays responses in order."""
    responses_iter = iter(responses)

    class _Transport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return next(responses_iter)

    return httpx.Client(transport=_Transport())


@pytest.fixture()
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


# ── fetch_themealdb_recipes ───────────────────────────────────────────────────

def test_fetch_normalizes_schema():
    meal = _make_meal("52772", "Teriyaki Chicken", "Chicken", "Japanese")
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    assert len(results) == 1
    r = results[0]
    assert r.source == "themealdb"
    assert r.source_id == "52772"
    assert r.url == "https://www.themealdb.com/meal/52772"
    assert "Teriyaki Chicken" in r.raw_content
    assert isinstance(r.fetched_at, datetime)


def test_fetch_raw_content_includes_instructions_and_ingredients():
    meal = _make_meal(instructions="Simmer for 30 minutes.", ingredients={"chicken": "500g", "soy sauce": "3/4 cup"})
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    content = results[0].raw_content
    assert "Simmer for 30 minutes" in content
    assert "chicken" in content
    assert "soy sauce" in content
    assert "Ingredients:" in content
    assert "Instructions:" in content


def test_fetch_source_handle_is_lowercased_category():
    meal = _make_meal(category="Chicken")
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    assert results[0].source_handle == "chicken"
    assert results[0].source_display_name == "Chicken"


def test_fetch_engagement_score_is_set():
    # _make_meal() has 2 ingredients and non-empty instructions → score > 0
    meal = _make_meal()
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    assert results[0].engagement_score is not None
    assert 0.0 < results[0].engagement_score <= 100.0


def test_fetch_engagement_score_zero_for_empty_recipe():
    meal = _make_meal(instructions="", ingredients={})
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    assert results[0].engagement_score == 0.0


def test_fetch_has_transcript_is_none():
    meal = _make_meal()
    client = _make_client([_make_response([meal])])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=5, client=client)

    assert results[0].has_transcript is None


def test_fetch_handles_null_meals_response():
    # TheMealDB returns {"meals": null} when no results found
    client = _make_client([_make_response(None)])

    results = fetch_themealdb_recipes(queries=["xyznotameal"], max_results=5, client=client)

    assert results == []


def test_fetch_deduplicates_across_queries():
    meal = _make_meal("52772", "Same Meal")
    client = _make_client([
        _make_response([meal]),
        _make_response([meal]),
    ])

    results = fetch_themealdb_recipes(queries=["chicken", "chicken again"], max_results=10, client=client)

    assert len(results) == 1


def test_fetch_respects_max_results():
    meals = [_make_meal(str(i), f"Meal {i}") for i in range(5)]
    client = _make_client([_make_response(meals)])

    results = fetch_themealdb_recipes(queries=["chicken"], max_results=3, client=client)

    assert len(results) == 3


def test_fetch_multiple_queries():
    meals_q1 = [_make_meal("1", "Chicken Soup")]
    meals_q2 = [_make_meal("2", "Pasta Carbonara", category="Pasta")]
    client = _make_client([_make_response(meals_q1), _make_response(meals_q2)])

    results = fetch_themealdb_recipes(queries=["chicken", "pasta"], max_results=10, client=client)

    assert len(results) == 2
    sources = {r.source_id for r in results}
    assert sources == {"1", "2"}


# ── save_themealdb_recipes ────────────────────────────────────────────────────

def test_save_persists_new_records(in_memory_db):
    meal = _make_meal("52772", "Teriyaki Chicken")
    client = _make_client([_make_response([meal])])

    saved = save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client)

    assert len(saved) == 1
    row = in_memory_db.query(RawRecipe).filter_by(source_id="52772").first()
    assert row is not None
    assert row.source == "themealdb"


def test_save_skips_duplicates(in_memory_db):
    meal = _make_meal("52772", "Teriyaki Chicken")

    client1 = _make_client([_make_response([meal])])
    save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client1)

    client2 = _make_client([_make_response([meal])])
    saved_again = save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client2)

    assert saved_again == []
    assert in_memory_db.query(RawRecipe).count() == 1


def test_save_creates_source_row(in_memory_db):
    meal = _make_meal("52772", "Teriyaki Chicken", category="Chicken")
    client = _make_client([_make_response([meal])])

    save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client)

    source = in_memory_db.query(Source).filter_by(platform="themealdb", handle="chicken").first()
    assert source is not None
    assert source.display_name == "Chicken"
    assert source.status == "active"


def test_save_stores_content_length(in_memory_db):
    meal = _make_meal("52772", "Teriyaki Chicken")
    client = _make_client([_make_response([meal])])

    save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client)

    row = in_memory_db.query(RawRecipe).filter_by(source_id="52772").first()
    assert row.content_length > 0


def test_save_links_recipe_to_source_fk(in_memory_db):
    meal = _make_meal("52772", "Teriyaki Chicken", category="Chicken")
    client = _make_client([_make_response([meal])])

    save_themealdb_recipes(in_memory_db, queries=["chicken"], max_results=5, client=client)

    source = in_memory_db.query(Source).filter_by(platform="themealdb", handle="chicken").first()
    row = in_memory_db.query(RawRecipe).filter_by(source_id="52772").first()
    assert row.source_fk == source.id

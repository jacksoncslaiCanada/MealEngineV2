"""Tests for the FastAPI routes (recipes + ingredients).

Uses FastAPI's TestClient with an in-memory SQLite database — no real
Postgres or network calls required.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Ingredient, RawRecipe, Source
from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# In-memory DB + TestClient setup
# ---------------------------------------------------------------------------

def _make_engine():
    """SQLite in-memory engine where all connections share one database."""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def client():
    engine = _make_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def seeded_client():
    """TestClient with a small set of pre-seeded recipes and ingredients."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    # Seed data
    db = TestSession()
    source = Source(
        platform="themealdb", handle="chicken",
        display_name="Chicken", status="active",
        added_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.flush()

    r1 = RawRecipe(
        source="themealdb", source_id="52772",
        raw_content="Meal: Teriyaki Chicken Casserole\n\nIngredients:\n- 3/4 cup soy sauce",
        url="https://www.themealdb.com/meal/52772",
        fetched_at=datetime.now(timezone.utc),
        source_fk=source.id,
        engagement_score=89.4,
        content_length=1792,
        has_transcript=None,
    )
    r2 = RawRecipe(
        source="youtube", source_id="abc123",
        raw_content="Easy pasta recipe",
        url="https://youtube.com/watch?v=abc123",
        fetched_at=datetime.now(timezone.utc),
        source_fk=source.id,
        engagement_score=72.1,
        content_length=100,
        has_transcript=True,
    )
    db.add_all([r1, r2])
    db.flush()

    ing1 = Ingredient(ingredient_name="soy sauce", quantity="3/4", unit="cup",
                      recipe_id=r1.id, source_id=source.id,
                      extracted_at=datetime.now(timezone.utc))
    ing2 = Ingredient(ingredient_name="chicken thighs", quantity="2", unit="lbs",
                      recipe_id=r1.id, source_id=source.id,
                      extracted_at=datetime.now(timezone.utc))
    ing3 = Ingredient(ingredient_name="broccoli", quantity=None, unit=None,
                      recipe_id=r1.id, source_id=source.id,
                      extracted_at=datetime.now(timezone.utc))
    db.add_all([ing1, ing2, ing3])
    db.commit()
    db.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /recipes
# ---------------------------------------------------------------------------

def test_list_recipes_empty(client):
    resp = client.get("/recipes")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_recipes_returns_all(seeded_client):
    resp = seeded_client.get("/recipes")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_recipes_filter_by_source(seeded_client):
    resp = seeded_client.get("/recipes?source=themealdb")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "themealdb"


def test_list_recipes_filter_unknown_source_returns_empty(seeded_client):
    resp = seeded_client.get("/recipes?source=reddit")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_recipes_pagination(seeded_client):
    resp = seeded_client.get("/recipes?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_recipes_response_shape(seeded_client):
    resp = seeded_client.get("/recipes")
    item = resp.json()[0]
    for field in ("id", "source", "source_id", "url", "fetched_at",
                  "engagement_score", "content_length", "has_transcript"):
        assert field in item, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# GET /recipes/{id}
# ---------------------------------------------------------------------------

def test_get_recipe_not_found(client):
    resp = client.get("/recipes/999")
    assert resp.status_code == 404


def test_get_recipe_returns_detail(seeded_client):
    # Get id from list first
    recipes = seeded_client.get("/recipes?source=themealdb").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_id"] == "52772"
    assert "ingredients" in data
    assert len(data["ingredients"]) == 3


def test_get_recipe_ingredients_embedded(seeded_client):
    recipes = seeded_client.get("/recipes?source=themealdb").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}")
    ingredients = resp.json()["ingredients"]
    names = {i["ingredient_name"] for i in ingredients}
    assert names == {"soy sauce", "chicken thighs", "broccoli"}


def test_get_recipe_no_ingredients_returns_empty_list(seeded_client):
    # r2 (youtube) has no ingredients
    recipes = seeded_client.get("/recipes?source=youtube").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}")
    assert resp.status_code == 200
    assert resp.json()["ingredients"] == []


# ---------------------------------------------------------------------------
# GET /recipes/{id}/ingredients
# ---------------------------------------------------------------------------

def test_get_recipe_ingredients_not_found(client):
    resp = client.get("/recipes/999/ingredients")
    assert resp.status_code == 404


def test_get_recipe_ingredients_returns_list(seeded_client):
    recipes = seeded_client.get("/recipes?source=themealdb").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}/ingredients")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


def test_get_recipe_ingredients_shape(seeded_client):
    recipes = seeded_client.get("/recipes?source=themealdb").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}/ingredients")
    item = resp.json()[0]
    for field in ("id", "ingredient_name", "quantity", "unit", "extracted_at"):
        assert field in item, f"Missing field: {field}"


def test_get_recipe_ingredients_null_quantity_unit(seeded_client):
    recipes = seeded_client.get("/recipes?source=themealdb").json()
    recipe_id = recipes[0]["id"]

    resp = seeded_client.get(f"/recipes/{recipe_id}/ingredients")
    broccoli = next(i for i in resp.json() if i["ingredient_name"] == "broccoli")
    assert broccoli["quantity"] is None
    assert broccoli["unit"] is None


# ---------------------------------------------------------------------------
# GET /ingredients/search
# ---------------------------------------------------------------------------

def test_search_ingredients_missing_name(client):
    resp = client.get("/ingredients/search")
    assert resp.status_code == 422  # missing required query param


def test_search_ingredients_finds_match(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=soy")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["ingredient_name"] == "soy sauce"


def test_search_ingredients_case_insensitive(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=SOY")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_search_ingredients_substring_match(seeded_client):
    # "chicken" should match "chicken thighs"
    resp = seeded_client.get("/ingredients/search?name=chicken")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["ingredient_name"] == "chicken thighs"


def test_search_ingredients_no_match(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=truffle")
    assert resp.status_code == 200
    assert resp.json() == []


def test_search_ingredients_response_shape(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=soy")
    item = resp.json()[0]
    for field in ("ingredient_name", "recipe_id", "recipe_source",
                  "recipe_url", "quantity", "unit"):
        assert field in item, f"Missing field: {field}"


def test_search_ingredients_includes_recipe_url(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=soy")
    assert "themealdb.com" in resp.json()[0]["recipe_url"]


def test_search_ingredients_pagination(seeded_client):
    resp = seeded_client.get("/ingredients/search?name=&limit=1&offset=0", params={"name": "o"})
    assert resp.status_code == 200
    assert len(resp.json()) <= 1

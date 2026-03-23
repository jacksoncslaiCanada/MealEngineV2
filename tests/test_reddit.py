"""Unit tests for the Reddit connector."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe
from app.connectors.reddit import fetch_reddit_recipes, save_reddit_recipes
from app.schemas import RawRecipeSchema


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_post(post_id: str, title: str, selftext: str, permalink: str, is_self=True) -> dict:
    return {
        "data": {
            "id": post_id,
            "title": title,
            "selftext": selftext,
            "permalink": permalink,
            "is_self": is_self,
        }
    }


def _make_response(posts: list[dict]):
    mock = MagicMock()
    mock.json.return_value = {"data": {"children": posts}}
    mock.raise_for_status = MagicMock()
    return mock


def _make_client(responses: list) -> MagicMock:
    client = MagicMock()
    client.get.side_effect = responses
    return client


@pytest.fixture()
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


# ── fetch_reddit_recipes ──────────────────────────────────────────────────────

def test_fetch_returns_only_self_posts():
    posts = [
        _make_post("link1", "Link post", "", "/r/recipes/link1", is_self=False),
        _make_post("self1", "Pasta recipe", "boil water", "/r/recipes/self1", is_self=True),
    ]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=10, client=client))

    assert len(results) == 1
    assert results[0].source_id == "self1"


def test_fetch_normalizes_schema():
    posts = [_make_post("abc123", "My Recipe", "1. Cook\n2. Eat", "/r/cooking/abc123")]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["cooking"], limit=5, client=client))

    r = results[0]
    assert r.source == "reddit"
    assert r.source_id == "abc123"
    assert r.url == "https://www.reddit.com/r/cooking/abc123"
    assert "My Recipe" in r.raw_content
    assert "Cook" in r.raw_content
    assert isinstance(r.fetched_at, datetime)


def test_fetch_title_only_when_no_selftext():
    posts = [_make_post("xyz", "Just a title", "", "/r/recipes/xyz")]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=5, client=client))
    assert results[0].raw_content == "Just a title"


def test_fetch_multiple_subreddits():
    posts_a = [_make_post("id1", "Recipe A", "body A", "/r/recipes/id1")]
    posts_b = [_make_post("id2", "Recipe B", "body B", "/r/cooking/id2")]
    client = _make_client([_make_response(posts_a), _make_response(posts_b)])

    results = list(fetch_reddit_recipes(subreddits=["recipes", "cooking"], limit=5, client=client))
    assert len(results) == 2


# ── save_reddit_recipes ───────────────────────────────────────────────────────

def test_save_persists_new_records(in_memory_db):
    posts = [_make_post("newid", "Saved Recipe", "great body", "/r/recipes/newid")]
    client = _make_client([_make_response(posts)])

    saved = save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, client=client)

    assert len(saved) == 1
    assert saved[0].source_id == "newid"
    row = in_memory_db.query(RawRecipe).filter_by(source_id="newid").first()
    assert row is not None
    assert row.source == "reddit"


def test_save_skips_duplicates(in_memory_db):
    posts = [_make_post("dup1", "Dup Recipe", "body", "/r/recipes/dup1")]

    save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, client=_make_client([_make_response(posts)]))
    saved_again = save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, client=_make_client([_make_response(posts)]))

    assert saved_again == []
    assert in_memory_db.query(RawRecipe).count() == 1

"""Unit tests for the Reddit connector."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe, Source
from app.connectors.reddit import fetch_reddit_recipes, save_reddit_recipes
from app.schemas import RawRecipeSchema


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_post(
    post_id: str,
    title: str,
    selftext: str,
    permalink: str,
    is_self=True,
    score: int = 100,
    upvote_ratio: float = 0.95,
) -> dict:
    return {
        "data": {
            "id": post_id,
            "title": title,
            "selftext": selftext,
            "permalink": permalink,
            "is_self": is_self,
            "score": score,
            "upvote_ratio": upvote_ratio,
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


def test_fetch_includes_source_handle():
    posts = [_make_post("h1", "Recipe", "body", "/r/EatCheapAndHealthy/h1")]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["EatCheapAndHealthy"], limit=5, client=client))
    assert results[0].source_handle == "EatCheapAndHealthy"
    assert results[0].source_display_name == "r/EatCheapAndHealthy"


def test_fetch_computes_engagement_score():
    posts = [_make_post("e1", "Popular Recipe", "great", "/r/recipes/e1", score=1000, upvote_ratio=0.98)]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=5, client=client))
    assert results[0].engagement_score is not None
    assert results[0].engagement_score > 0


def test_fetch_zero_score_gives_zero_engagement():
    posts = [_make_post("e2", "New Recipe", "body", "/r/recipes/e2", score=0, upvote_ratio=0.0)]
    client = _make_client([_make_response(posts)])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=5, client=client))
    assert results[0].engagement_score == 0.0


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


def test_save_creates_source_row(in_memory_db):
    posts = [_make_post("s1", "Recipe", "body", "/r/cooking/s1")]
    client = _make_client([_make_response(posts)])

    save_reddit_recipes(in_memory_db, subreddits=["cooking"], limit=5, client=client)

    source = in_memory_db.query(Source).filter_by(platform="reddit", handle="cooking").first()
    assert source is not None
    assert source.display_name == "r/cooking"
    assert source.status == "active"


def test_save_stores_engagement_and_content_length(in_memory_db):
    posts = [_make_post("s2", "Recipe", "some body text", "/r/recipes/s2", score=500, upvote_ratio=0.9)]
    client = _make_client([_make_response(posts)])

    save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, client=client)

    row = in_memory_db.query(RawRecipe).filter_by(source_id="s2").first()
    assert row.engagement_score is not None
    assert row.engagement_score > 0
    assert row.content_length > 0


def test_save_links_recipe_to_source_fk(in_memory_db):
    posts = [_make_post("s3", "Recipe", "body", "/r/food/s3")]
    client = _make_client([_make_response(posts)])

    save_reddit_recipes(in_memory_db, subreddits=["food"], limit=5, client=client)

    source = in_memory_db.query(Source).filter_by(platform="reddit", handle="food").first()
    row = in_memory_db.query(RawRecipe).filter_by(source_id="s3").first()
    assert row.source_fk == source.id

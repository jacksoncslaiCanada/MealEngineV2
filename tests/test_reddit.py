"""Unit tests for the Reddit connector."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe
from app.connectors.reddit import fetch_reddit_recipes, save_reddit_recipes
from app.schemas import RawRecipeSchema


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_submission(post_id: str, title: str, selftext: str, permalink: str, is_self=True):
    sub = MagicMock()
    sub.id = post_id
    sub.title = title
    sub.selftext = selftext
    sub.permalink = permalink
    sub.is_self = is_self
    return sub


def _make_reddit_mock(submissions: list) -> MagicMock:
    reddit = MagicMock()
    reddit.subreddit.return_value.hot.return_value = submissions
    return reddit


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
    link_post = _make_submission("link1", "Link post", "", "/r/recipes/link1", is_self=False)
    self_post = _make_submission("self1", "Pasta recipe", "boil water, add pasta", "/r/recipes/self1", is_self=True)
    reddit = _make_reddit_mock([link_post, self_post])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=10, reddit=reddit))

    assert len(results) == 1
    assert results[0].source_id == "self1"


def test_fetch_normalizes_schema():
    submission = _make_submission("abc123", "My Recipe", "1. Cook it\n2. Eat it", "/r/cooking/abc123")
    reddit = _make_reddit_mock([submission])

    results = list(fetch_reddit_recipes(subreddits=["cooking"], limit=5, reddit=reddit))

    assert len(results) == 1
    r = results[0]
    assert r.source == "reddit"
    assert r.source_id == "abc123"
    assert r.url == "https://www.reddit.com/r/cooking/abc123"
    assert "My Recipe" in r.raw_content
    assert "Cook it" in r.raw_content
    assert isinstance(r.fetched_at, datetime)


def test_fetch_title_only_when_no_selftext():
    submission = _make_submission("xyz", "Just a title", "", "/r/recipes/xyz")
    reddit = _make_reddit_mock([submission])

    results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=5, reddit=reddit))
    assert results[0].raw_content == "Just a title"


def test_fetch_multiple_subreddits():
    sub1 = _make_submission("id1", "Recipe A", "body A", "/r/recipes/id1")
    sub2 = _make_submission("id2", "Recipe B", "body B", "/r/cooking/id2")

    reddit = MagicMock()
    reddit.subreddit("recipes").hot.return_value = [sub1]
    reddit.subreddit("cooking").hot.return_value = [sub2]

    results = list(fetch_reddit_recipes(subreddits=["recipes", "cooking"], limit=5, reddit=reddit))
    assert len(results) == 2


# ── save_reddit_recipes ───────────────────────────────────────────────────────

def test_save_persists_new_records(in_memory_db):
    submission = _make_submission("newid", "Saved Recipe", "great recipe body", "/r/recipes/newid")
    reddit = _make_reddit_mock([submission])

    saved = save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, reddit=reddit)

    assert len(saved) == 1
    assert saved[0].source_id == "newid"

    row = in_memory_db.query(RawRecipe).filter_by(source_id="newid").first()
    assert row is not None
    assert row.source == "reddit"


def test_save_skips_duplicates(in_memory_db):
    submission = _make_submission("dup1", "Duplicate Recipe", "body", "/r/recipes/dup1")
    reddit = _make_reddit_mock([submission])

    save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, reddit=reddit)

    # fetch same data again
    reddit2 = _make_reddit_mock([submission])
    saved_again = save_reddit_recipes(in_memory_db, subreddits=["recipes"], limit=5, reddit=reddit2)

    assert saved_again == []
    assert in_memory_db.query(RawRecipe).count() == 1

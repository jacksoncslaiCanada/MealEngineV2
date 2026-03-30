"""Unit tests for the RSS connector."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.connectors.rss import (
    _build_raw_content,
    _entry_content,
    _entry_id,
    _feed_handle,
    fetch_rss_recipes,
    save_rss_recipes,
)
from app.db.base import Base


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_entry(
    id="entry-123",
    title="Quick Mapo Tofu",
    link="https://thewoksoflife.com/mapo-tofu/",
    summary="A spicy Sichuan classic.",
    content=None,
) -> SimpleNamespace:
    entry = SimpleNamespace(
        id=id,
        title=title,
        link=link,
        summary=summary,
    )
    if content is not None:
        entry.content = [{"value": content}]
    return entry


def _make_feed(entries=None, feed_title="The Woks of Life"):
    parsed = SimpleNamespace(
        feed=SimpleNamespace(title=feed_title),
        entries=entries or [],
    )
    return parsed


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ── _entry_id ─────────────────────────────────────────────────────────────────

def test_entry_id_uses_id_field():
    entry = _make_entry(id="https://thewoksoflife.com/?p=123")
    assert _entry_id(entry) == "https://thewoksoflife.com/?p=123"


def test_entry_id_hashes_link_when_no_id():
    entry = _make_entry(id=None, link="https://thewoksoflife.com/mapo-tofu/")
    result = _entry_id(entry)
    assert len(result) == 16
    assert result.isalnum()


def test_entry_id_stable_for_same_link():
    entry1 = _make_entry(id=None, link="https://example.com/recipe")
    entry2 = _make_entry(id=None, link="https://example.com/recipe")
    assert _entry_id(entry1) == _entry_id(entry2)


def test_entry_id_different_for_different_links():
    e1 = _make_entry(id=None, link="https://example.com/a")
    e2 = _make_entry(id=None, link="https://example.com/b")
    assert _entry_id(e1) != _entry_id(e2)


# ── _entry_content ────────────────────────────────────────────────────────────

def test_entry_content_prefers_content_field():
    entry = _make_entry(summary="short summary", content="Full article body here.")
    assert _entry_content(entry) == "Full article body here."


def test_entry_content_falls_back_to_summary():
    entry = _make_entry(summary="A spicy Sichuan classic.")
    assert _entry_content(entry) == "A spicy Sichuan classic."


def test_entry_content_empty_when_neither():
    entry = SimpleNamespace(summary="", title="x", id="x", link="x")
    assert _entry_content(entry) == ""


# ── _build_raw_content ────────────────────────────────────────────────────────

def test_build_raw_content_includes_title_and_content():
    entry = _make_entry(title="Mapo Tofu", summary="Spicy tofu dish.")
    raw = _build_raw_content(entry)
    assert raw.startswith("Title: Mapo Tofu")
    assert "Spicy tofu dish." in raw


def test_build_raw_content_skips_content_if_empty():
    entry = SimpleNamespace(title="No body", summary="", id="x", link="x")
    raw = _build_raw_content(entry)
    assert raw == "Title: No body"


# ── _feed_handle ──────────────────────────────────────────────────────────────

def test_feed_handle_strips_www():
    assert _feed_handle("https://www.thewoksoflife.com/feed/") == "thewoksoflife.com"


def test_feed_handle_no_www():
    assert _feed_handle("https://thewoksoflife.com/feed/") == "thewoksoflife.com"


# ── fetch_rss_recipes ─────────────────────────────────────────────────────────

@patch("app.connectors.rss.feedparser.parse")
def test_fetch_returns_one_record_per_entry(mock_parse):
    entries = [_make_entry(id=f"id-{i}", title=f"Recipe {i}") for i in range(3)]
    mock_parse.return_value = _make_feed(entries=entries)

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert len(records) == 3


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_respects_max_results(mock_parse):
    entries = [_make_entry(id=f"id-{i}") for i in range(10)]
    mock_parse.return_value = _make_feed(entries=entries)

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"], max_results=3)

    assert len(records) == 3


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_sets_source_rss(mock_parse):
    mock_parse.return_value = _make_feed(entries=[_make_entry()])

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert records[0].source == "rss"


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_sets_correct_handle(mock_parse):
    mock_parse.return_value = _make_feed(entries=[_make_entry()])

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert records[0].source_handle == "thewoksoflife.com"


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_sets_display_name_from_feed_title(mock_parse):
    mock_parse.return_value = _make_feed(entries=[_make_entry()], feed_title="The Woks of Life")

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert records[0].source_display_name == "The Woks of Life"


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_engagement_proportional_to_content_length(mock_parse):
    short_entry = _make_entry(id="short", summary="Short.")
    long_entry = _make_entry(id="long", summary="A " * 500)
    mock_parse.return_value = _make_feed(entries=[short_entry, long_entry])

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])
    short_rec = next(r for r in records if r.source_id == "short")
    long_rec = next(r for r in records if r.source_id == "long")

    assert long_rec.engagement_score > short_rec.engagement_score


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_engagement_capped_at_80(mock_parse):
    very_long = _make_entry(id="huge", summary="word " * 10_000)
    mock_parse.return_value = _make_feed(entries=[very_long])

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert records[0].engagement_score == 80.0


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_has_transcript_is_false(mock_parse):
    mock_parse.return_value = _make_feed(entries=[_make_entry()])

    records = fetch_rss_recipes(feed_urls=["https://thewoksoflife.com/feed/"])

    assert records[0].has_transcript is False


@patch("app.connectors.rss.feedparser.parse")
def test_fetch_aggregates_multiple_feeds(mock_parse):
    mock_parse.side_effect = [
        _make_feed(entries=[_make_entry(id="a1"), _make_entry(id="a2")]),
        _make_feed(entries=[_make_entry(id="b1")]),
    ]

    records = fetch_rss_recipes(
        feed_urls=["https://feed-a.com/feed/", "https://feed-b.com/feed/"]
    )

    assert len(records) == 3


# ── save_rss_recipes ──────────────────────────────────────────────────────────

@patch("app.connectors.rss.feedparser.parse")
def test_save_inserts_new_records(mock_parse, db):
    mock_parse.return_value = _make_feed(entries=[_make_entry(id="new-1")])

    saved = save_rss_recipes(db, feed_urls=["https://thewoksoflife.com/feed/"])

    assert len(saved) == 1
    assert saved[0].source_id == "new-1"


@patch("app.connectors.rss.feedparser.parse")
def test_save_skips_duplicates(mock_parse, db):
    entries = [_make_entry(id="dup-1")]
    mock_parse.return_value = _make_feed(entries=entries)

    save_rss_recipes(db, feed_urls=["https://thewoksoflife.com/feed/"])
    # Second call — same entry should be skipped
    mock_parse.return_value = _make_feed(entries=entries)
    saved2 = save_rss_recipes(db, feed_urls=["https://thewoksoflife.com/feed/"])

    assert len(saved2) == 0


@patch("app.connectors.rss.feedparser.parse")
def test_save_creates_source_row(mock_parse, db):
    mock_parse.return_value = _make_feed(entries=[_make_entry(id="src-1")])

    save_rss_recipes(db, feed_urls=["https://thewoksoflife.com/feed/"])

    from app.db.models import Source
    source = db.query(Source).filter_by(platform="rss", handle="thewoksoflife.com").first()
    assert source is not None


@patch("app.connectors.rss.feedparser.parse")
def test_save_returns_empty_list_for_empty_feed(mock_parse, db):
    mock_parse.return_value = _make_feed(entries=[])

    saved = save_rss_recipes(db, feed_urls=["https://thewoksoflife.com/feed/"])

    assert saved == []

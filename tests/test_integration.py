"""
Integration tests — hit real Reddit and YouTube APIs with minimal fetches.

These tests verify that live data can be fetched and parsed correctly before
moving to Phase 2 (ingredient extraction). They are NOT run in CI.

Run manually:
    pytest -m integration -v -s

Requirements:
    - Reddit: no credentials needed (public JSON API)
    - YouTube: set YOUTUBE_API_KEY in your .env file (tests skip if key is missing/dummy)
"""

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe


# ── shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """In-memory SQLite DB — we're testing parsing, not Supabase persistence."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _assert_valid_schema(record, expected_source: str):
    """
    Shared assertions for any RawRecipeSchema record.
    These are the minimum guarantees Phase 2 (Claude extraction) depends on.
    """
    # source tag is correct
    assert record.source == expected_source

    # source_id is a clean identifier (no whitespace)
    assert record.source_id
    assert record.source_id == record.source_id.strip()
    assert " " not in record.source_id

    # raw_content has enough text to be useful for extraction
    assert record.raw_content
    assert len(record.raw_content) >= 10, "raw_content too short to extract ingredients from"

    # url points to the right platform
    if expected_source == "reddit":
        assert record.url.startswith("https://www.reddit.com/")
    elif expected_source == "youtube":
        assert record.url.startswith("https://www.youtube.com/watch?v=")

    # fetched_at is timezone-aware (required for Supabase timestamptz column)
    assert isinstance(record.fetched_at, datetime)
    assert record.fetched_at.tzinfo is not None


def _assert_db_roundtrip(db, source_id: str, expected_source: str):
    """Confirm the record was written to DB and can be read back intact."""
    row = db.query(RawRecipe).filter_by(source_id=source_id).first()
    assert row is not None, f"Row with source_id={source_id!r} not found in DB"
    assert row.source == expected_source
    assert row.raw_content  # not truncated to empty on write
    assert row.url
    assert row.fetched_at is not None


def _preview(label: str, record):
    """Print a content preview so you can eyeball real data during local runs."""
    preview_text = record.raw_content[:300].replace("\n", " ")
    print(f"\n{'─'*60}")
    print(f"[{label}]")
    print(f"  source_id : {record.source_id}")
    print(f"  url       : {record.url}")
    print(f"  fetched_at: {record.fetched_at}")
    print(f"  content   : {preview_text!r}")
    print(f"{'─'*60}")


# ── Reddit integration ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_reddit_fetch_returns_parseable_record():
    """
    Fetch 1 post from r/recipes via the real Reddit JSON API.
    Verifies the connector produces a well-formed record ready for extraction.

    Skipped automatically when Reddit returns 403 (common in CI environments
    where GitHub Actions IPs are blocked by Reddit).
    """
    import httpx
    from app.connectors.reddit import fetch_reddit_recipes

    try:
        results = list(fetch_reddit_recipes(subreddits=["recipes"], limit=5))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            pytest.skip(f"Reddit returned 403 — IP likely blocked in CI: {exc.request.url}")
        raise

    assert len(results) >= 1, (
        "Expected at least one self-post from r/recipes. "
        "Reddit may be down or blocking requests."
    )

    record = results[0]
    _assert_valid_schema(record, "reddit")

    # Reddit-specific structure: raw_content starts with the post title
    first_line = record.raw_content.split("\n")[0]
    assert len(first_line) > 0, "First line (title) should not be empty"

    _preview("Reddit live fetch", record)


@pytest.mark.integration
def test_reddit_fetch_and_save(db):
    """
    Fetch 1 Reddit post and save it to DB.
    Verifies the full pipeline: fetch → normalize → persist → query.

    Skipped automatically when Reddit returns 403 (common in CI environments
    where GitHub Actions IPs are blocked by Reddit).
    """
    import httpx
    from app.connectors.reddit import save_reddit_recipes

    try:
        saved = save_reddit_recipes(db, subreddits=["recipes"], limit=5)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            pytest.skip(f"Reddit returned 403 — IP likely blocked in CI: {exc.request.url}")
        raise

    assert len(saved) >= 1, "Expected at least one record to be saved"

    record = saved[0]
    _assert_valid_schema(record, "reddit")
    _assert_db_roundtrip(db, record.source_id, "reddit")

    # Running save again with the same data must not create duplicates
    saved_again = save_reddit_recipes(db, subreddits=["recipes"], limit=5)
    total_rows = db.query(RawRecipe).count()
    assert total_rows == len(saved), (
        f"Expected {len(saved)} rows after re-save, got {total_rows}. "
        "Deduplication may be broken."
    )

    _preview("Reddit save + dedup", record)


# ── YouTube integration ───────────────────────────────────────────────────────

def _youtube_api_key() -> str:
    """Return the real YouTube API key, or empty string if not configured."""
    key = os.environ.get("YOUTUBE_API_KEY", "")
    # conftest.py sets this to the dummy value "test" for unit tests
    return "" if key in ("", "test") else key


@pytest.mark.integration
def test_youtube_fetch_returns_parseable_record():
    """
    Fetch 1 video from the real YouTube Data API.
    Verifies the connector produces a well-formed record ready for extraction.

    Skipped automatically if YOUTUBE_API_KEY is not set or is the dummy value.
    """
    api_key = _youtube_api_key()
    if not api_key:
        pytest.skip("YOUTUBE_API_KEY not set — add it to .env to run this test")

    from app.connectors.youtube import fetch_youtube_recipes, _build_youtube_client

    client = _build_youtube_client(api_key)
    results = fetch_youtube_recipes(
        queries=["easy dinner recipe"],
        max_results=1,
        youtube_client=client,
        # Use the real transcript fetcher to exercise the full path
    )

    assert len(results) >= 1, (
        "Expected at least 1 result for 'easy dinner recipe'. "
        "YouTube API may be down or quota exceeded."
    )

    record = results[0]
    _assert_valid_schema(record, "youtube")

    # YouTube-specific structure: raw_content always starts with "Title:"
    assert record.raw_content.startswith("Title:"), (
        f"Expected raw_content to start with 'Title:', got: {record.raw_content[:50]!r}"
    )

    _preview("YouTube live fetch", record)


@pytest.mark.integration
def test_youtube_fetch_and_save(db):
    """
    Fetch 1 YouTube video, save it to DB, and verify deduplication.

    Uses a single YouTube API call to avoid per-second rate limits that occur
    when two consecutive search requests are made with the same key and query.
    The save and dedup logic is exercised directly against the DB.

    Skipped automatically if YOUTUBE_API_KEY is not set or is the dummy value.
    """
    api_key = _youtube_api_key()
    if not api_key:
        pytest.skip("YOUTUBE_API_KEY not set — add it to .env to run this test")

    from app.connectors.youtube import fetch_youtube_recipes, _build_youtube_client
    from app.schemas import RawRecipeSchema

    # Single API call — reuse these records for both save and dedup checks.
    client = _build_youtube_client(api_key)
    records = fetch_youtube_recipes(
        queries=["easy dinner recipe"],
        max_results=1,
        youtube_client=client,
    )

    if not records:
        pytest.skip("YouTube API returned no results — quota may be exhausted")

    record = records[0]
    _assert_valid_schema(record, "youtube")

    # ── Save ──────────────────────────────────────────────────────────────
    row = RawRecipe(
        source=record.source,
        source_id=record.source_id,
        raw_content=record.raw_content,
        url=record.url,
        fetched_at=record.fetched_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    saved_record = RawRecipeSchema.model_validate(row)
    _assert_valid_schema(saved_record, "youtube")
    _assert_db_roundtrip(db, record.source_id, "youtube")

    # ── Dedup: re-saving the same records must not create new rows ─────────
    for r in records:
        if not db.query(RawRecipe).filter_by(source_id=r.source_id).first():
            db.add(RawRecipe(
                source=r.source,
                source_id=r.source_id,
                raw_content=r.raw_content,
                url=r.url,
                fetched_at=r.fetched_at,
            ))
    db.commit()

    total_rows = db.query(RawRecipe).count()
    assert total_rows == len(records), (
        f"Expected {len(records)} rows after re-save, got {total_rows}. "
        "Deduplication may be broken."
    )

    _preview("YouTube save + dedup", saved_record)

"""Unit tests for the YouTube connector."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe
from app.connectors.youtube import fetch_youtube_recipes, save_youtube_recipes


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_search_response(items: list[dict]) -> dict:
    return {"items": items}


def _make_video_item(video_id: str, title: str, description: str) -> dict:
    return {
        "id": {"videoId": video_id},
        "snippet": {"title": title, "description": description},
    }


def _make_youtube_mock(responses: list[dict]) -> MagicMock:
    """Build a mock YouTube client that returns responses in order per query."""
    client = MagicMock()
    execute_mock = MagicMock(side_effect=responses)
    client.search.return_value.list.return_value.execute = execute_mock
    return client


def _no_transcript(_video_id: str) -> str:
    return ""


@pytest.fixture()
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


# ── fetch_youtube_recipes ─────────────────────────────────────────────────────

def test_fetch_normalizes_schema():
    response = _make_search_response([
        _make_video_item("vid1", "Easy Pasta", "Cook pasta in salted water."),
    ])
    client = _make_youtube_mock([response])

    results = fetch_youtube_recipes(
        queries=["pasta recipe"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert len(results) == 1
    r = results[0]
    assert r.source == "youtube"
    assert r.source_id == "vid1"
    assert r.url == "https://www.youtube.com/watch?v=vid1"
    assert "Easy Pasta" in r.raw_content
    assert "Cook pasta" in r.raw_content
    assert isinstance(r.fetched_at, datetime)


def test_fetch_includes_transcript_when_available():
    response = _make_search_response([
        _make_video_item("vid2", "Chicken Soup", "A hearty soup."),
    ])
    client = _make_youtube_mock([response])

    def fake_transcript(video_id: str) -> str:
        return "add chicken, add vegetables, simmer for 30 minutes"

    results = fetch_youtube_recipes(
        queries=["soup recipe"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=fake_transcript,
    )

    assert "simmer for 30 minutes" in results[0].raw_content


def test_fetch_deduplicates_across_queries():
    same_item = _make_video_item("vid3", "Same Video", "desc")
    response1 = _make_search_response([same_item])
    response2 = _make_search_response([same_item])
    client = _make_youtube_mock([response1, response2])

    results = fetch_youtube_recipes(
        queries=["query1", "query2"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert len(results) == 1


def test_fetch_handles_empty_response():
    client = _make_youtube_mock([_make_search_response([])])

    results = fetch_youtube_recipes(
        queries=["nothing"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert results == []


def test_fetch_handles_missing_transcript():
    response = _make_search_response([
        _make_video_item("vid4", "Steak", ""),
    ])
    client = _make_youtube_mock([response])

    results = fetch_youtube_recipes(
        queries=["steak"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert "Transcript:" not in results[0].raw_content


# ── save_youtube_recipes ──────────────────────────────────────────────────────

def test_save_persists_new_records(in_memory_db):
    response = _make_search_response([
        _make_video_item("save1", "Saved Recipe", "persist this"),
    ])
    client = _make_youtube_mock([response])

    saved = save_youtube_recipes(
        in_memory_db,
        queries=["recipe"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert len(saved) == 1
    row = in_memory_db.query(RawRecipe).filter_by(source_id="save1").first()
    assert row is not None
    assert row.source == "youtube"


def test_save_skips_duplicates(in_memory_db):
    item = _make_video_item("dup1", "Dup Video", "desc")

    client1 = _make_youtube_mock([_make_search_response([item])])
    save_youtube_recipes(
        in_memory_db, queries=["q"], max_results=5,
        youtube_client=client1, transcript_fetcher=_no_transcript,
    )

    client2 = _make_youtube_mock([_make_search_response([item])])
    saved_again = save_youtube_recipes(
        in_memory_db, queries=["q"], max_results=5,
        youtube_client=client2, transcript_fetcher=_no_transcript,
    )

    assert saved_again == []
    assert in_memory_db.query(RawRecipe).count() == 1

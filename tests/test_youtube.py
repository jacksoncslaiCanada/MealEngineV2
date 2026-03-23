"""Unit tests for the YouTube connector."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe, Source
from app.connectors.youtube import fetch_youtube_recipes, save_youtube_recipes


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_search_response(items: list[dict]) -> dict:
    return {"items": items}


def _make_video_item(
    video_id: str,
    title: str,
    description: str,
    channel_id: str = "UCTestChannel",
    channel_title: str = "Test Channel",
) -> dict:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": title,
            "description": description,
            "channelId": channel_id,
            "channelTitle": channel_title,
        },
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


def test_fetch_includes_source_handle_and_display_name():
    response = _make_search_response([
        _make_video_item("vid5", "Tacos", "desc", channel_id="UCTacoChannel", channel_title="Taco Master"),
    ])
    client = _make_youtube_mock([response])

    results = fetch_youtube_recipes(
        queries=["tacos"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert results[0].source_handle == "UCTacoChannel"
    assert results[0].source_display_name == "Taco Master"


def test_fetch_sets_has_transcript_flag():
    response = _make_search_response([_make_video_item("vid6", "Pizza", "desc")])
    client = _make_youtube_mock([response])

    def has_transcript(_vid: str) -> str:
        return "mix dough and bake"

    results = fetch_youtube_recipes(
        queries=["pizza"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=has_transcript,
    )

    assert results[0].has_transcript is True


def test_fetch_has_transcript_false_when_missing():
    response = _make_search_response([_make_video_item("vid7", "Salad", "desc")])
    client = _make_youtube_mock([response])

    results = fetch_youtube_recipes(
        queries=["salad"],
        max_results=5,
        youtube_client=client,
        transcript_fetcher=_no_transcript,
    )

    assert results[0].has_transcript is False


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


def test_save_creates_source_row(in_memory_db):
    response = _make_search_response([
        _make_video_item("sv1", "Recipe", "desc", channel_id="UCTest123", channel_title="Test Chef"),
    ])
    client = _make_youtube_mock([response])

    save_youtube_recipes(
        in_memory_db, queries=["recipe"], max_results=5,
        youtube_client=client, transcript_fetcher=_no_transcript,
    )

    source = in_memory_db.query(Source).filter_by(platform="youtube", handle="UCTest123").first()
    assert source is not None
    assert source.display_name == "Test Chef"
    assert source.status == "active"


def test_save_stores_content_length_and_transcript_flag(in_memory_db):
    response = _make_search_response([
        _make_video_item("sv2", "Recipe", "nice description"),
    ])
    client = _make_youtube_mock([response])

    def with_transcript(_vid: str) -> str:
        return "step 1 cook step 2 serve"

    save_youtube_recipes(
        in_memory_db, queries=["recipe"], max_results=5,
        youtube_client=client, transcript_fetcher=with_transcript,
    )

    row = in_memory_db.query(RawRecipe).filter_by(source_id="sv2").first()
    assert row.content_length > 0
    assert row.has_transcript is True


def test_save_links_recipe_to_source_fk(in_memory_db):
    response = _make_search_response([
        _make_video_item("sv3", "Recipe", "desc", channel_id="UCLinkTest"),
    ])
    client = _make_youtube_mock([response])

    save_youtube_recipes(
        in_memory_db, queries=["recipe"], max_results=5,
        youtube_client=client, transcript_fetcher=_no_transcript,
    )

    source = in_memory_db.query(Source).filter_by(platform="youtube", handle="UCLinkTest").first()
    row = in_memory_db.query(RawRecipe).filter_by(source_id="sv3").first()
    assert row.source_fk == source.id

"""Unit tests for the discovery sweep module."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Source
from app.discovery import (
    DiscoverySummary,
    _is_cooking_adjacent,
    discover_reddit_sources,
    discover_youtube_sources,
    run_discovery_sweep,
)


# ── fixtures & helpers ────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _active_reddit_source(db, handle: str) -> Source:
    source = Source(
        platform="reddit",
        handle=handle,
        display_name=f"r/{handle}",
        status="active",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _make_reddit_response(posts: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"data": {"children": posts}}
    mock.raise_for_status = MagicMock()
    return mock


def _make_reddit_post(subreddit: str, author: str = "user1") -> dict:
    return {"data": {"subreddit": subreddit, "author": author, "is_self": True}}


def _url_dispatch_client(url_map: dict[str, dict]) -> MagicMock:
    """
    Build an httpx mock whose .get() dispatches based on URL substring.

    url_map keys are URL substrings; values are the raw dict returned by .json().
    If multiple keys match, the longest match wins.
    """
    client = MagicMock()

    def get_side_effect(url, **kwargs):
        matches = {k: v for k, v in url_map.items() if k in url}
        if not matches:
            raise ValueError(f"No mock configured for URL: {url}")
        best_key = max(matches, key=len)
        mock_resp = MagicMock()
        mock_resp.json.return_value = matches[best_key]
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    client.get.side_effect = get_side_effect
    return client


# ── _is_cooking_adjacent ──────────────────────────────────────────────────────

def test_cooking_adjacent_true():
    assert _is_cooking_adjacent("veganrecipes") is True
    assert _is_cooking_adjacent("MealPrepSunday") is True
    assert _is_cooking_adjacent("food") is True
    assert _is_cooking_adjacent("Cooking") is True
    assert _is_cooking_adjacent("EatCheapAndHealthy") is True


def test_cooking_adjacent_false():
    assert _is_cooking_adjacent("worldnews") is False
    assert _is_cooking_adjacent("gaming") is False
    assert _is_cooking_adjacent("programming") is False
    assert _is_cooking_adjacent("fitness") is False
    assert _is_cooking_adjacent("AskCulinary") is False  # "culinary" not in keyword list


# ── Reddit discovery — Direction 1 (author cross-posting) ────────────────────

def test_reddit_discovers_new_subreddit_from_author(db):
    source = _active_reddit_source(db, "EatCheapAndHealthy")

    # Hot feed: author "u/chefpro" posts in our source
    hot_feed = {"data": {"children": [
        {"data": {"author": "chefpro", "subreddit": "EatCheapAndHealthy", "is_self": True}},
    ]}}
    # chefpro's history: they also post in "veganrecipes"
    user_history = {"data": {"children": [
        {"data": {"subreddit": "veganrecipes", "author": "chefpro"}},
    ]}}
    # Keyword search: no results
    empty_search = {"data": {"children": []}}

    client = _url_dispatch_client({
        "EatCheapAndHealthy/hot": hot_feed,
        "/user/chefpro": user_history,
        "/search": empty_search,
    })

    result = discover_reddit_sources(db, client=client, active_sources=[source])

    assert result.new_candidates == 1
    new = db.query(Source).filter_by(platform="reddit", handle="veganrecipes").first()
    assert new is not None
    assert new.status == "candidate"


def test_reddit_skips_non_cooking_subreddit(db):
    source = _active_reddit_source(db, "recipes")

    hot_feed = {"data": {"children": [
        {"data": {"author": "user1", "subreddit": "recipes", "is_self": True}},
    ]}}
    user_history = {"data": {"children": [
        {"data": {"subreddit": "worldnews", "author": "user1"}},
        {"data": {"subreddit": "gaming", "author": "user1"}},
    ]}}
    empty_search = {"data": {"children": []}}

    client = _url_dispatch_client({
        "recipes/hot": hot_feed,
        "/user/user1": user_history,
        "/search": empty_search,
    })

    result = discover_reddit_sources(db, client=client, active_sources=[source])

    assert result.new_candidates == 0


def test_reddit_skips_already_tracked_subreddit(db):
    source = _active_reddit_source(db, "cooking")
    # "recipes" is already in the db
    existing = Source(platform="reddit", handle="recipes", display_name="r/recipes", status="active")
    db.add(existing)
    db.commit()

    hot_feed = {"data": {"children": [
        {"data": {"author": "user1", "subreddit": "cooking", "is_self": True}},
    ]}}
    user_history = {"data": {"children": [
        {"data": {"subreddit": "recipes", "author": "user1"}},  # already tracked
    ]}}
    empty_search = {"data": {"children": []}}

    client = _url_dispatch_client({
        "cooking/hot": hot_feed,
        "/user/user1": user_history,
        "/search": empty_search,
    })

    result = discover_reddit_sources(db, client=client, active_sources=[source])

    assert result.new_candidates == 0


def test_reddit_skips_deleted_authors(db):
    source = _active_reddit_source(db, "food")

    hot_feed = {"data": {"children": [
        {"data": {"author": "[deleted]", "subreddit": "food", "is_self": True}},
    ]}}
    empty_search = {"data": {"children": []}}

    client = _url_dispatch_client({
        "food/hot": hot_feed,
        "/search": empty_search,
    })

    result = discover_reddit_sources(db, client=client, active_sources=[source])

    # No user history calls should have been made for [deleted]
    assert result.new_candidates == 0


def test_reddit_discovers_no_new_sources_when_no_active_sources(db):
    # No active sources in DB
    empty_search = {"data": {"children": []}}
    client = _url_dispatch_client({"/search": empty_search})

    result = discover_reddit_sources(db, client=client, active_sources=[])

    assert result.new_candidates == 0


# ── Reddit discovery — Direction 2 (keyword search) ──────────────────────────

def test_reddit_discovers_from_keyword_search(db):
    # No active sources needed for direction 2
    # "mealprep" subreddit appears 4 times across search results
    search_results = {"data": {"children": [
        {"data": {"subreddit": "mealprep", "author": "a"}},
        {"data": {"subreddit": "mealprep", "author": "b"}},
        {"data": {"subreddit": "mealprep", "author": "c"}},
        {"data": {"subreddit": "mealprep", "author": "d"}},
    ]}}
    # Both search terms return the same set of subreddits
    client = _url_dispatch_client({"/search": search_results})

    result = discover_reddit_sources(db, client=client, active_sources=[])

    assert result.new_candidates == 1
    new = db.query(Source).filter_by(platform="reddit", handle="mealprep").first()
    assert new is not None
    assert new.status == "candidate"


def test_reddit_search_below_threshold_not_inserted(db):
    # "bread" appears only once per search term (2 terms × 1 hit = 2 total),
    # which is below the default threshold of 3.
    search_results = {"data": {"children": [
        {"data": {"subreddit": "bread", "author": "a"}},
    ]}}
    client = _url_dispatch_client({"/search": search_results})

    result = discover_reddit_sources(db, client=client, active_sources=[])

    assert result.new_candidates == 0
    assert db.query(Source).count() == 0


def test_reddit_search_deduplicates_across_terms(db):
    # Same subreddit appears in both "recipe" and "cooking" searches
    search_results = {"data": {"children": [
        {"data": {"subreddit": "sourdough", "author": "a"}},
        {"data": {"subreddit": "sourdough", "author": "b"}},
        {"data": {"subreddit": "sourdough", "author": "c"}},
    ]}}
    client = _url_dispatch_client({"/search": search_results})

    result = discover_reddit_sources(db, client=client, active_sources=[])

    assert result.new_candidates == 1
    assert db.query(Source).count() == 1


# ── YouTube discovery ─────────────────────────────────────────────────────────

def _make_yt_mock(
    search_items: list[dict],         # initial search results (all queries return same)
    channel_video_count: int,
    recent_video_ids: list[str],
    video_stats: list[dict],          # [{videoId: .., statistics: {viewCount, likeCount}}, ...]
) -> MagicMock:
    """Build a YouTube client mock for discovery tests."""
    client = MagicMock()

    # search().list() can be called in two ways:
    # 1. Initial search: q=... → returns search_items
    # 2. Per-channel recent videos: channelId=... → returns recent_video_ids as items
    def search_list_side_effect(**kwargs):
        mock_execute = MagicMock()
        if "channelId" in kwargs:
            # Recent video search for a specific channel
            mock_execute.execute.return_value = {
                "items": [
                    {"id": {"videoId": vid}, "snippet": {}}
                    for vid in recent_video_ids
                ]
            }
        else:
            # Initial broad search
            mock_execute.execute.return_value = {"items": search_items}
        return mock_execute

    client.search.return_value.list.side_effect = search_list_side_effect

    # channels().list()
    client.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"statistics": {"videoCount": str(channel_video_count)}}]
    }

    # videos().list()
    client.videos.return_value.list.return_value.execute.return_value = {
        "items": video_stats
    }

    return client


def test_youtube_discovers_candidate_channel(db):
    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCNew", "channelTitle": "New Chef"}}
    ]
    video_stats = [
        {"statistics": {"viewCount": "1000", "likeCount": "50"}},
        {"statistics": {"viewCount": "800", "likeCount": "40"}},
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=10,
        recent_video_ids=["v1", "v2"],
        video_stats=video_stats,
    )

    result = discover_youtube_sources(db, youtube_client=client)

    # Engagement for 1000 views / 50 likes is well below 60 out of 100 → candidate
    assert db.query(Source).filter_by(handle="UCNew").count() == 1
    source = db.query(Source).filter_by(handle="UCNew").first()
    assert source.status in ("candidate", "active")  # depends on exact score
    assert source.display_name == "New Chef"


def test_youtube_auto_promotes_high_engagement_channel(db):
    # Extremely high view + like counts → engagement_score > 75 → quality > 0.75 → active
    # Need ~100M views to push log10-based score above 75
    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCHot", "channelTitle": "Hot Chef"}}
    ]
    video_stats = [
        {"statistics": {"viewCount": "100000000", "likeCount": "10000000"}},
        {"statistics": {"viewCount": "80000000", "likeCount": "8000000"}},
        {"statistics": {"viewCount": "70000000", "likeCount": "7000000"}},
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=50,
        recent_video_ids=["v1", "v2", "v3"],
        video_stats=video_stats,
    )

    result = discover_youtube_sources(db, youtube_client=client)

    source = db.query(Source).filter_by(handle="UCHot").first()
    assert source is not None
    assert source.status == "active"
    assert result.auto_promoted == 1
    assert result.new_candidates == 0


def test_youtube_candidate_stays_candidate_with_low_engagement(db):
    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCLow", "channelTitle": "Low Chef"}}
    ]
    # Very low views → engagement near zero → quality well below 0.6
    video_stats = [
        {"statistics": {"viewCount": "5", "likeCount": "1"}},
        {"statistics": {"viewCount": "3", "likeCount": "0"}},
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=6,
        recent_video_ids=["v1", "v2"],
        video_stats=video_stats,
    )

    result = discover_youtube_sources(db, youtube_client=client)

    source = db.query(Source).filter_by(handle="UCLow").first()
    assert source.status == "candidate"
    assert result.new_candidates == 1
    assert result.auto_promoted == 0


def test_youtube_skips_channel_with_too_few_videos(db):
    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCSmall", "channelTitle": "Small Chef"}}
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=2,   # below default min of 5
        recent_video_ids=["v1"],
        video_stats=[],
    )

    result = discover_youtube_sources(db, youtube_client=client)

    assert db.query(Source).filter_by(handle="UCSmall").count() == 0
    assert result.skipped == 1
    assert result.new_candidates == 0


def test_youtube_skips_already_tracked_channel(db):
    existing = Source(
        platform="youtube", handle="UCKnown", display_name="Known Chef", status="active"
    )
    db.add(existing)
    db.commit()

    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCKnown", "channelTitle": "Known Chef"}}
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=50,
        recent_video_ids=["v1"],
        video_stats=[{"statistics": {"viewCount": "100000", "likeCount": "5000"}}],
    )

    result = discover_youtube_sources(db, youtube_client=client)

    # No new sources — UCKnown was already known
    assert db.query(Source).count() == 1
    assert result.new_candidates == 0
    assert result.auto_promoted == 0


def test_youtube_stores_quality_score(db):
    search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCScore", "channelTitle": "Score Chef"}}
    ]
    video_stats = [
        {"statistics": {"viewCount": "5000000", "likeCount": "400000"}},
    ]
    client = _make_yt_mock(
        search_items=search_items,
        channel_video_count=20,
        recent_video_ids=["v1"],
        video_stats=video_stats,
    )

    discover_youtube_sources(db, youtube_client=client)

    source = db.query(Source).filter_by(handle="UCScore").first()
    assert source.quality_score is not None
    assert 0.0 < source.quality_score <= 1.0


# ── run_discovery_sweep (orchestrator) ───────────────────────────────────────

def test_run_discovery_sweep_combines_summaries(db):
    # Reddit: keyword search finds "pastarecipes" (3 hits)
    search_results = {"data": {"children": [
        {"data": {"subreddit": "pastarecipes", "author": "a"}},
        {"data": {"subreddit": "pastarecipes", "author": "b"}},
        {"data": {"subreddit": "pastarecipes", "author": "c"}},
    ]}}
    reddit_client = _url_dispatch_client({"/search": search_results})

    # YouTube: new channel, too few videos → skipped
    yt_search_items = [
        {"id": {"videoId": "v1"}, "snippet": {"channelId": "UCTiny", "channelTitle": "Tiny"}}
    ]
    yt_client = _make_yt_mock(
        search_items=yt_search_items,
        channel_video_count=1,  # below min → skipped
        recent_video_ids=[],
        video_stats=[],
    )

    summary = run_discovery_sweep(db, reddit_client=reddit_client, youtube_client=yt_client)

    assert summary.new_candidates == 1   # the Reddit subreddit
    assert summary.auto_promoted == 0
    assert summary.skipped == 1          # the YouTube channel
    assert len(summary.new_sources) == 1


def test_run_discovery_sweep_returns_discovery_summary(db):
    empty_search = {"data": {"children": []}}
    reddit_client = _url_dispatch_client({"/search": empty_search})

    yt_client = _make_yt_mock(
        search_items=[],
        channel_video_count=0,
        recent_video_ids=[],
        video_stats=[],
    )

    result = run_discovery_sweep(db, reddit_client=reddit_client, youtube_client=yt_client)

    assert isinstance(result, DiscoverySummary)
    assert result.new_candidates == 0
    assert result.auto_promoted == 0

"""Unit tests for the scoring module."""

import math
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import RawRecipe, Source
from app.scoring import (
    compute_reddit_engagement,
    compute_youtube_engagement,
    recompute_source_scores,
    auto_promote_candidates,
    get_or_create_source,
    mark_source_ingested,
)


@pytest.fixture()
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    yield db
    db.close()
    Base.metadata.drop_all(engine)


def _make_source(db, platform="reddit", handle="recipes", status="active") -> Source:
    source = Source(
        platform=platform,
        handle=handle,
        display_name=f"r/{handle}",
        status=status,
        added_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _make_recipe(db, source: Source, engagement_score: float | None) -> RawRecipe:
    row = RawRecipe(
        source=source.platform,
        source_id=f"id_{id(engagement_score)}_{len(db.query(RawRecipe).all())}",
        raw_content="Recipe content",
        url="https://example.com",
        fetched_at=datetime.now(timezone.utc),
        source_fk=source.id,
        engagement_score=engagement_score,
        content_length=14,
    )
    db.add(row)
    db.commit()
    return row


# ── compute_reddit_engagement ─────────────────────────────────────────────────

def test_reddit_engagement_zero_score():
    assert compute_reddit_engagement(score=0, upvote_ratio=1.0) == 0.0


def test_reddit_engagement_negative_score():
    assert compute_reddit_engagement(score=-5, upvote_ratio=0.5) == 0.0


def test_reddit_engagement_typical_post():
    result = compute_reddit_engagement(score=1000, upvote_ratio=0.95)
    assert 0 < result <= 100


def test_reddit_engagement_capped_at_100():
    # score=10^10 → log10(10^10+1)*1.0*10 > 100, so min() clamps to 100
    result = compute_reddit_engagement(score=10_000_000_000, upvote_ratio=1.0)
    assert result == 100.0


def test_reddit_engagement_increases_with_score():
    low = compute_reddit_engagement(score=10, upvote_ratio=0.9)
    high = compute_reddit_engagement(score=10_000, upvote_ratio=0.9)
    assert high > low


def test_reddit_engagement_decreases_with_lower_ratio():
    good = compute_reddit_engagement(score=500, upvote_ratio=0.95)
    poor = compute_reddit_engagement(score=500, upvote_ratio=0.50)
    assert good > poor


# ── compute_youtube_engagement ────────────────────────────────────────────────

def test_youtube_engagement_zero_views():
    assert compute_youtube_engagement(views=0, likes=1000) == 0.0


def test_youtube_engagement_typical_video():
    result = compute_youtube_engagement(views=500_000, likes=20_000)
    assert 0 < result <= 100


def test_youtube_engagement_capped_at_100():
    # views=10^11 → log10(10^11+1)*like_ratio*10 ≈ 110 > 100, so min() clamps to 100
    result = compute_youtube_engagement(views=100_000_000_000, likes=100_000_000_000)
    assert result == 100.0


def test_youtube_engagement_increases_with_views():
    low = compute_youtube_engagement(views=100, likes=10)
    high = compute_youtube_engagement(views=1_000_000, likes=10)
    assert high > low


# ── recompute_source_scores ───────────────────────────────────────────────────

def test_recompute_scores_single_source(in_memory_db):
    source = _make_source(in_memory_db, handle="cooking")
    _make_recipe(in_memory_db, source, engagement_score=80.0)
    _make_recipe(in_memory_db, source, engagement_score=60.0)

    updated = recompute_source_scores(in_memory_db, window=10, decay=0.9)

    assert len(updated) == 1
    assert updated[0].quality_score is not None
    assert 0.0 < updated[0].quality_score <= 1.0


def test_recompute_scores_ignores_null_engagement(in_memory_db):
    source = _make_source(in_memory_db, handle="food")
    _make_recipe(in_memory_db, source, engagement_score=None)

    updated = recompute_source_scores(in_memory_db, window=10, decay=0.9)

    # No recipes with engagement data — source score should not be updated
    assert len(updated) == 0


def test_recompute_scores_skips_rejected_sources(in_memory_db):
    source = _make_source(in_memory_db, handle="spam", status="rejected")
    _make_recipe(in_memory_db, source, engagement_score=50.0)

    updated = recompute_source_scores(in_memory_db, window=10, decay=0.9)

    assert len(updated) == 0


def test_recompute_scores_uses_recency_weighting(in_memory_db):
    source = _make_source(in_memory_db, handle="trending")
    # Older post has very high engagement
    _make_recipe(in_memory_db, source, engagement_score=100.0)
    # Newer post has low engagement — recency weighting should pull score down
    _make_recipe(in_memory_db, source, engagement_score=10.0)

    recompute_source_scores(in_memory_db, window=10, decay=0.9)
    in_memory_db.refresh(source)

    # Score should be closer to 10/100=0.10 (recent) than 100/100=1.0 (old)
    # With decay=0.9: weights [1.0, 0.9], weighted avg = (10*1.0 + 100*0.9)/(1.0+0.9) = 100/1.9 ≈ 52.6
    expected_approx = (10 * 1.0 + 100 * 0.9) / (1.0 + 0.9) / 100
    assert abs(source.quality_score - expected_approx) < 0.01


# ── auto_promote_candidates ───────────────────────────────────────────────────

def test_auto_promote_above_threshold(in_memory_db):
    candidate = _make_source(in_memory_db, handle="good_sub", status="candidate")
    candidate.quality_score = 0.75
    in_memory_db.commit()

    promoted = auto_promote_candidates(in_memory_db, threshold=0.6)

    assert len(promoted) == 1
    assert promoted[0].handle == "good_sub"
    assert promoted[0].status == "active"


def test_auto_promote_below_threshold_stays_candidate(in_memory_db):
    candidate = _make_source(in_memory_db, handle="weak_sub", status="candidate")
    candidate.quality_score = 0.4
    in_memory_db.commit()

    promoted = auto_promote_candidates(in_memory_db, threshold=0.6)

    assert promoted == []
    assert candidate.status == "candidate"


def test_auto_promote_does_not_touch_active_sources(in_memory_db):
    active = _make_source(in_memory_db, handle="already_active", status="active")
    active.quality_score = 0.9
    in_memory_db.commit()

    promoted = auto_promote_candidates(in_memory_db, threshold=0.6)

    assert promoted == []


# ── get_or_create_source ──────────────────────────────────────────────────────

def test_get_or_create_inserts_new_source(in_memory_db):
    source = get_or_create_source(in_memory_db, platform="reddit", handle="veganrecipes")

    assert source.id is not None
    assert source.platform == "reddit"
    assert source.handle == "veganrecipes"
    assert source.status == "active"


def test_get_or_create_returns_existing_source(in_memory_db):
    first = get_or_create_source(in_memory_db, platform="reddit", handle="cooking")
    second = get_or_create_source(in_memory_db, platform="reddit", handle="cooking")

    assert first.id == second.id
    assert in_memory_db.query(Source).count() == 1


def test_get_or_create_uses_provided_display_name(in_memory_db):
    source = get_or_create_source(
        in_memory_db, platform="youtube", handle="UCTest", display_name="Test Chef"
    )
    assert source.display_name == "Test Chef"


# ── mark_source_ingested ──────────────────────────────────────────────────────

def test_mark_source_ingested_updates_fields(in_memory_db):
    source = _make_source(in_memory_db)
    assert source.last_ingested_at is None
    assert source.content_count == 0

    mark_source_ingested(in_memory_db, source, new_content_count=5)

    assert source.last_ingested_at is not None
    assert source.content_count == 5


def test_mark_source_ingested_increments_count(in_memory_db):
    source = _make_source(in_memory_db)
    source.content_count = 10
    in_memory_db.commit()

    mark_source_ingested(in_memory_db, source, new_content_count=3)

    assert source.content_count == 13

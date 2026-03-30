"""Unit tests for the weekly pipeline orchestrator.

These tests patch the individual components (connectors, scoring, discovery)
to verify only the orchestration logic — that every step is called correctly,
results are wired into the report, and errors are captured rather than crashing.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Source
from app.discovery import DiscoverySummary
from app.pipeline import PipelineReport, run_weekly_pipeline
from app.schemas import RawRecipeSchema
from datetime import datetime, timezone


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_schema(source_id: str, platform: str = "reddit") -> RawRecipeSchema:
    return RawRecipeSchema(
        source=platform,
        source_id=source_id,
        raw_content="content",
        url="https://example.com",
        fetched_at=datetime.now(timezone.utc),
    )


def _make_source(platform: str = "reddit", handle: str = "recipes") -> MagicMock:
    s = MagicMock(spec=Source)
    s.platform = platform
    s.handle = handle
    s.display_name = f"r/{handle}"
    return s


def _empty_discovery() -> DiscoverySummary:
    return DiscoverySummary(new_candidates=0, auto_promoted=0, skipped=0)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def patch_new_connectors():
    """Patch TheMealDB and RSS connectors for all pipeline tests."""
    with (
        patch("app.pipeline.save_themealdb_recipes", return_value=[]) as mock_mdb,
        patch("app.pipeline.save_rss_recipes", return_value=[]) as mock_rss,
    ):
        yield mock_mdb, mock_rss


# ── orchestration ─────────────────────────────────────────────────────────────

@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_calls_all_steps(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote,
    db, patch_new_connectors,
):
    mock_mdb, mock_rss = patch_new_connectors
    run_weekly_pipeline(db)

    mock_reddit.assert_called_once()
    mock_youtube.assert_called_once()
    mock_mdb.assert_called_once()
    mock_rss.assert_called_once()
    mock_rescore.assert_called_once_with(db)
    mock_discover.assert_called_once()
    mock_promote.assert_called_once_with(db)


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[_make_schema("yt1", "youtube")])
@patch("app.pipeline.save_reddit_recipes", return_value=[_make_schema("r1"), _make_schema("r2")])
def test_pipeline_report_counts(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    assert report.reddit_new == 2
    assert report.youtube_new == 1
    assert report.themealdb_new == 0
    assert report.rss_new == 0
    assert report.total_new == 3


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_rss_recipes", return_value=[_make_schema("rss1", "rss")])
@patch("app.pipeline.save_themealdb_recipes", return_value=[_make_schema("mdb1", "themealdb"), _make_schema("mdb2", "themealdb")])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_report_themealdb_and_rss_counts(
    mock_reddit, mock_youtube, mock_mdb, mock_rss, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    assert report.themealdb_new == 2
    assert report.rss_new == 1
    assert report.total_new == 3


@patch("app.pipeline.auto_promote_candidates", return_value=[_make_source()])
@patch("app.pipeline.run_discovery_sweep", return_value=DiscoverySummary(
    new_candidates=2, auto_promoted=1, skipped=0
))
@patch("app.pipeline.recompute_source_scores", return_value=[MagicMock(), MagicMock()])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_report_discovery_and_promote_counts(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    assert report.sources_rescored == 2
    assert report.discovery.new_candidates == 2
    assert report.discovery.auto_promoted == 1
    assert len(report.promoted) == 1


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_returns_pipeline_report(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    result = run_weekly_pipeline(db)
    assert isinstance(result, PipelineReport)
    assert result.elapsed_seconds >= 0


# ── active source selection ───────────────────────────────────────────────────

@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_passes_active_reddit_handles_to_connector(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    # Insert two active Reddit sources
    for handle in ("recipes", "cooking"):
        db.add(Source(
            platform="reddit", handle=handle,
            display_name=f"r/{handle}", status="active",
        ))
    db.commit()

    run_weekly_pipeline(db)

    call_kwargs = mock_reddit.call_args
    subreddits_arg = call_kwargs.kwargs.get("subreddits") or call_kwargs.args[1]
    assert set(subreddits_arg) == {"recipes", "cooking"}


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_skips_paused_and_rejected_reddit_sources(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    db.add(Source(platform="reddit", handle="active_sub", display_name="r/active_sub", status="active"))
    db.add(Source(platform="reddit", handle="paused_sub", display_name="r/paused_sub", status="paused"))
    db.add(Source(platform="reddit", handle="banned_sub", display_name="r/banned_sub", status="rejected"))
    db.commit()

    run_weekly_pipeline(db)

    call_kwargs = mock_reddit.call_args
    subreddits_arg = call_kwargs.kwargs.get("subreddits") or call_kwargs.args[1]
    assert "active_sub" in subreddits_arg
    assert "paused_sub" not in subreddits_arg
    assert "banned_sub" not in subreddits_arg


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_uses_default_subreddits_when_registry_empty(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    # No sources in DB — should pass None so the connector uses its defaults
    run_weekly_pipeline(db)

    call_kwargs = mock_reddit.call_args
    assert call_kwargs.kwargs.get("subreddits") is None


# ── error handling ────────────────────────────────────────────────────────────

@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", side_effect=Exception("Reddit blocked"))
def test_pipeline_captures_reddit_error_and_continues(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    # Pipeline should not crash — error is captured in the report
    assert len(report.errors) == 1
    assert "Reddit" in report.errors[0]
    # YouTube and remaining steps still ran
    mock_youtube.assert_called_once()
    mock_rescore.assert_called_once()
    mock_discover.assert_called_once()
    mock_promote.assert_called_once()


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", side_effect=Exception("Quota exceeded"))
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_captures_youtube_error_and_continues(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    assert len(report.errors) == 1
    assert "YouTube" in report.errors[0]
    mock_rescore.assert_called_once()
    mock_discover.assert_called_once()


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", side_effect=Exception("YT error"))
@patch("app.pipeline.save_reddit_recipes", side_effect=Exception("Reddit error"))
def test_pipeline_captures_both_errors(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)

    assert len(report.errors) == 2


@patch("app.pipeline.auto_promote_candidates", return_value=[])
@patch("app.pipeline.run_discovery_sweep", return_value=_empty_discovery())
@patch("app.pipeline.recompute_source_scores", return_value=[])
@patch("app.pipeline.save_youtube_recipes", return_value=[])
@patch("app.pipeline.save_reddit_recipes", return_value=[])
def test_pipeline_no_errors_gives_empty_error_list(
    mock_reddit, mock_youtube, mock_rescore, mock_discover, mock_promote, db
):
    report = run_weekly_pipeline(db)
    assert report.errors == []

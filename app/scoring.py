"""Source scoring — engagement formulas, source quality computation, and candidate promotion."""

import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import RawRecipe, Source


# ── Engagement score formulas ─────────────────────────────────────────────────
#
# Both formulas use a log scale so viral outliers don't dominate.
# A post with 10,000 upvotes is not 1,000× more valuable than one with 10 —
# the curve flattens, giving a more useful signal for quality scoring.
# Output range: 0–100.

def compute_reddit_engagement(score: int, upvote_ratio: float) -> float:
    """
    Compute a 0–100 engagement score from Reddit post metrics.

    Args:
        score: Reddit post score (upvotes minus downvotes).
        upvote_ratio: Fraction of votes that were upvotes (0.0–1.0).
    """
    if score <= 0:
        return 0.0
    return min(math.log10(score + 1) * upvote_ratio * 10, 100.0)


def compute_youtube_engagement(views: int, likes: int) -> float:
    """
    Compute a 0–100 engagement score from YouTube video metrics.

    Args:
        views: Total view count.
        likes: Total like count.
    """
    if views <= 0:
        return 0.0
    like_ratio = likes / (likes + 1)  # avoids needing dislike count; asymptotes to 1.0
    return min(math.log10(views + 1) * like_ratio * 10, 100.0)


# ── Source quality scoring ────────────────────────────────────────────────────

def recompute_source_scores(
    db: Session,
    window: int | None = None,
    decay: float | None = None,
) -> list[Source]:
    """
    Recompute quality_score for all active and candidate sources that have content.

    Uses a recency-weighted average of engagement_score across the last `window`
    recipes from each source. More recent recipes have higher weight (exponential decay).

    quality_score is stored as 0.0–1.0 (engagement_score / 100).

    Returns the list of sources whose scores were updated.
    """
    if window is None:
        window = settings.source_score_window
    if decay is None:
        decay = settings.source_score_decay

    updated: list[Source] = []
    sources = (
        db.query(Source)
        .filter(Source.status.in_(["active", "candidate"]))
        .all()
    )

    for source in sources:
        recent = (
            db.query(RawRecipe)
            .filter(RawRecipe.source_fk == source.id)
            .filter(RawRecipe.engagement_score.isnot(None))
            .order_by(RawRecipe.fetched_at.desc())
            .limit(window)
            .all()
        )
        if not recent:
            continue

        weights = [decay ** i for i in range(len(recent))]
        total_weight = sum(weights)
        weighted_sum = sum(
            r.engagement_score * w
            for r, w in zip(recent, weights)
        )
        source.quality_score = round((weighted_sum / total_weight) / 100.0, 4)
        updated.append(source)

    db.commit()
    return updated


# ── Candidate promotion ───────────────────────────────────────────────────────

def auto_promote_candidates(
    db: Session,
    threshold: float | None = None,
) -> list[Source]:
    """
    Promote candidate sources whose quality_score exceeds the threshold to active.

    Returns the list of newly promoted sources.
    """
    if threshold is None:
        threshold = settings.source_quality_threshold

    candidates = (
        db.query(Source)
        .filter(
            Source.status == "candidate",
            Source.quality_score >= threshold,
        )
        .all()
    )
    for source in candidates:
        source.status = "active"
    db.commit()
    return candidates


# ── Source registry helpers ───────────────────────────────────────────────────

def get_or_create_source(
    db: Session,
    platform: str,
    handle: str,
    display_name: str | None = None,
    initial_status: str = "active",
) -> Source:
    """
    Return the Source row for (platform, handle), creating it if it does not exist.

    New sources created here are considered known-good (status='active') because
    they come from the curated connector source lists. Discovery-found candidates
    are inserted separately with status='candidate'.
    """
    source = db.query(Source).filter_by(platform=platform, handle=handle).first()
    if source:
        return source

    source = Source(
        platform=platform,
        handle=handle,
        display_name=display_name or handle,
        status=initial_status,
        quality_score=None,
        content_count=0,
        added_at=datetime.now(timezone.utc),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def mark_source_ingested(db: Session, source: Source, new_content_count: int) -> None:
    """Update last_ingested_at and increment content_count after a successful ingest run."""
    source.last_ingested_at = datetime.now(timezone.utc)
    source.content_count += new_content_count
    db.commit()

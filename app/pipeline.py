"""Weekly pipeline — orchestrates the four-step Sunday run.

Sequence
--------
1. Ingest   — pull new content from all active sources
2. Score    — recompute quality_score for each source from recent engagement
3. Discover — sweep for new candidate channels / subreddits
4. Promote  — auto-promote candidates whose quality_score crossed the threshold
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.orm import Session


import anthropic

from app.config import settings
from app.connectors.reddit import save_reddit_recipes
from app.connectors.rss import save_rss_recipes
from app.connectors.themealdb import save_themealdb_recipes
from app.connectors.youtube import save_youtube_recipes
from app.db.models import Source
from app.discovery import DiscoverySummary, run_discovery_sweep
from app.extractor import extract_all_unprocessed
from app.schemas import RawRecipeSchema
from app.scoring import auto_promote_candidates, recompute_source_scores

logger = logging.getLogger(__name__)


# ── Report type ───────────────────────────────────────────────────────────────

@dataclass
class PipelineReport:
    reddit_new: int
    youtube_new: int
    sources_rescored: int
    discovery: DiscoverySummary
    promoted: list[Source]
    elapsed_seconds: float
    ingredients_extracted: int = 0
    themealdb_new: int = 0
    rss_new: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_new(self) -> int:
        return self.reddit_new + self.youtube_new + self.themealdb_new + self.rss_new

    def log(self) -> None:
        logger.info(
            "Pipeline complete in %.1fs — "
            "ingested %d new recipes (%d Reddit, %d YouTube, %d TheMealDB, %d RSS), "
            "extracted %d ingredients, "
            "rescored %d sources, "
            "%d new candidates, %d auto-promoted",
            self.elapsed_seconds,
            self.total_new, self.reddit_new, self.youtube_new,
            self.themealdb_new, self.rss_new,
            self.ingredients_extracted,
            self.sources_rescored,
            self.discovery.new_candidates, self.discovery.auto_promoted,
        )
        print(
            f"\n=== Weekly Pipeline Complete ({self.elapsed_seconds:.1f}s) ===\n"
            f"  Ingested   : {self.total_new} new recipes "
            f"({self.reddit_new} Reddit, {self.youtube_new} YouTube, "
            f"{self.themealdb_new} TheMealDB, {self.rss_new} RSS)\n"
            f"  Extracted  : {self.ingredients_extracted} ingredient(s)\n"
            f"  Rescored   : {self.sources_rescored} sources\n"
            f"  Discovered : {self.discovery.new_candidates} new candidates, "
            f"{self.discovery.auto_promoted} auto-promoted, "
            f"{self.discovery.skipped} skipped\n"
            f"  Promoted   : {len(self.promoted)} candidates → active"
        )
        if self.errors:
            print(f"  Errors     : {len(self.errors)}")
            for err in self.errors:
                print(f"    - {err}")


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_weekly_pipeline(
    db: Session,
    reddit_client: httpx.Client | None = None,
    youtube_client: Any = None,
    anthropic_client: anthropic.Anthropic | None = None,
) -> PipelineReport:
    """
    Run the full weekly pipeline.

    Steps
    -----
    1. **Ingest** — fetch new content from all active sources:
       - Reddit: one feed per active subreddit in the sources table
       - YouTube: standard recipe search queries (query-based ingestion)
    2. **Score** — recompute quality_score for every active/candidate source
       using a recency-weighted average of their last 20 engagement scores.
    3. **Discover** — run the discovery sweep to find new candidate sources.
    4. **Promote** — auto-promote candidates whose quality_score now exceeds
       the configured threshold.

    Args:
        db: Database session.
        reddit_client: Optional httpx.Client for Reddit (injected in tests).
        youtube_client: Optional googleapiclient resource (injected in tests).

    Returns:
        A PipelineReport summarising what happened.
    """
    start = time.monotonic()
    errors: list[str] = []

    # ── Step 1: Ingest ────────────────────────────────────────────────────────
    print("Step 1/4 — Ingesting content from active sources...")

    # Reddit: pull from every active subreddit in the registry.
    # Falls back to the hardcoded default list if the registry is empty.
    active_reddit = (
        db.query(Source)
        .filter_by(platform="reddit", status="active")
        .all()
    )
    reddit_handles = [s.handle for s in active_reddit] or None

    reddit_saved: list[RawRecipeSchema] = []
    try:
        reddit_saved = save_reddit_recipes(
            db, subreddits=reddit_handles, client=reddit_client
        )
        print(f"  Reddit: {len(reddit_saved)} new recipes")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            logger.warning(
                "Reddit ingest skipped — runner IP blocked by Reddit CDN (403). "
                "Pipeline continues. Re-run from a non-Actions environment to ingest Reddit."
            )
            print("  Reddit: skipped (403 CDN block)")
        else:
            msg = f"Reddit ingest failed: {exc}"
            logger.exception(msg)
            errors.append(msg)
    except Exception as exc:  # noqa: BLE001
        msg = f"Reddit ingest failed: {exc}"
        logger.exception(msg)
        errors.append(msg)

    # YouTube: query-based ingestion captures content from the channels
    # that appear in recipe search results.  Channel-specific fetching
    # (one search per active channel) is a future enhancement.
    youtube_saved: list[RawRecipeSchema] = []
    try:
        youtube_saved = save_youtube_recipes(db, youtube_client=youtube_client)
        print(f"  YouTube: {len(youtube_saved)} new recipes")
    except Exception as exc:  # noqa: BLE001
        msg = f"YouTube ingest failed: {exc}"
        logger.exception(msg)
        errors.append(msg)

    # TheMealDB: free public API — no credentials required.
    themealdb_saved: list[RawRecipeSchema] = []
    try:
        themealdb_saved = save_themealdb_recipes(db)
        print(f"  TheMealDB: {len(themealdb_saved)} new recipes")
    except Exception as exc:  # noqa: BLE001
        msg = f"TheMealDB ingest failed: {exc}"
        logger.exception(msg)
        errors.append(msg)

    # RSS feeds: food blogs (Woks of Life, etc.)
    rss_saved: list[RawRecipeSchema] = []
    try:
        rss_saved = save_rss_recipes(db)
        print(f"  RSS: {len(rss_saved)} new recipes")
    except Exception as exc:  # noqa: BLE001
        msg = f"RSS ingest failed: {exc}"
        logger.exception(msg)
        errors.append(msg)

    # ── Step 2: Extract ingredients ───────────────────────────────────────────
    print("Step 2/5 — Extracting ingredients from new recipes...")
    ingredients_extracted = 0
    if not settings.anthropic_api_key:
        print("  Skipped — ANTHROPIC_API_KEY not configured")
        logger.warning("Ingredient extraction skipped: ANTHROPIC_API_KEY not set")
    else:
        try:
            if anthropic_client is None:
                anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            extracted = extract_all_unprocessed(db, client=anthropic_client)
            ingredients_extracted = len(extracted)
            print(f"  Extracted {ingredients_extracted} ingredient(s) from unprocessed recipes")
        except Exception as exc:  # noqa: BLE001
            msg = f"Ingredient extraction failed: {exc}"
            logger.exception(msg)
            errors.append(msg)
            # Recover the session so subsequent steps can still run
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass

    # ── Step 3: Score ─────────────────────────────────────────────────────────
    print("Step 3/5 — Recomputing source quality scores...")
    rescored = recompute_source_scores(db)
    print(f"  Rescored {len(rescored)} sources")

    # ── Step 4: Discover ──────────────────────────────────────────────────────
    print("Step 4/5 — Running discovery sweep...")
    discovery = run_discovery_sweep(
        db,
        reddit_client=reddit_client,
        youtube_client=youtube_client,
    )

    # ── Step 5: Promote ───────────────────────────────────────────────────────
    print("Step 5/5 — Promoting high-scoring candidates...")
    promoted = auto_promote_candidates(db)
    if promoted:
        for source in promoted:
            print(f"  Promoted: {source.display_name} ({source.platform})")

    elapsed = time.monotonic() - start
    report = PipelineReport(
        reddit_new=len(reddit_saved),
        youtube_new=len(youtube_saved),
        themealdb_new=len(themealdb_saved),
        rss_new=len(rss_saved),
        ingredients_extracted=ingredients_extracted,
        sources_rescored=len(rescored),
        discovery=discovery,
        promoted=promoted,
        elapsed_seconds=elapsed,
        errors=errors,
    )
    report.log()
    return report

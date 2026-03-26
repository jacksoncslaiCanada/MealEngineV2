#!/usr/bin/env python
"""
Production smoke test for Phase 1.

Checks:
  1. Schema integrity  — all expected columns are present on `sources` and
                         `raw_recipes` in the live database.
  2. Reddit ingest     — connector writes ≥1 real row (r/recipes, limit=5).
                         A 403 from Reddit (known GitHub runner IP block) is
                         recorded as a warning, not a failure.
  3. TheMealDB ingest  — connector writes ≥1 real row (no credentials needed;
                         always runs).
  4. YouTube ingest    — connector writes ≥1 real row (skipped when
                         SKIP_YOUTUBE=true or YOUTUBE_API_KEY is absent).
  5. FK integrity      — every row we inserted has a non-NULL `source_fk`.
  6. Quality scoring   — recompute_source_scores() updates quality_score for
                         at least one source (YouTube and TheMealDB sources
                         are scored when engagement_score is available).

All rows written by this test are deleted in the finally block.
A Markdown report is written to smoke_test_report.md; the workflow uploads
it as an artifact and pipes it into the GitHub step summary.

Usage
-----
    python scripts/smoke_test.py            # auto-skips YouTube if no key
    SKIP_YOUTUBE=true python scripts/smoke_test.py
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import inspect as sa_inspect

from app.config import settings
from app.db.models import RawRecipe, Source
from app.db.session import SessionLocal, engine
from app.connectors.reddit import save_reddit_recipes
from app.connectors.themealdb import save_themealdb_recipes
from app.connectors.youtube import save_youtube_recipes
from app.scoring import recompute_source_scores

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

REPORT_PATH = Path("smoke_test_report.md")

EXPECTED_COLUMNS = {
    "sources": {
        "id", "platform", "handle", "display_name", "status",
        "quality_score", "content_count", "added_at", "last_ingested_at",
    },
    "raw_recipes": {
        "id", "source", "source_id", "raw_content", "url", "fetched_at",
        "source_fk", "engagement_score", "content_length", "has_transcript",
    },
}

# Check result states
PASS = "pass"
FAIL = "fail"
WARN = "warn"   # environmental / known limitation — does not fail the overall run

_ICONS = {PASS: "✅", FAIL: "❌", WARN: "⚠️"}


# ── Smoke test runner ──────────────────────────────────────────────────────────

class SmokeTestRunner:
    def __init__(self, db, skip_youtube: bool = False):
        self.db = db
        self.skip_youtube = skip_youtube
        self.checks: list[dict] = []
        # platform source_ids (not DB PKs) of every recipe we insert
        self.inserted_platform_ids: list[str] = []
        # source PKs that existed before this test started
        self.pre_existing_source_pks: set[int] = set()
        # set to True when Reddit returns 403 so scoring can be downgraded to WARN
        self.reddit_blocked: bool = False

    # ── Recording helpers ──────────────────────────────────────────────────────

    def record(self, name: str, passed: bool, detail: str) -> bool:
        state = PASS if passed else FAIL
        icon = _ICONS[state]
        self.checks.append({"name": name, "state": state, "detail": detail})
        log.log(logging.INFO if passed else logging.ERROR, "%s %s: %s", icon, name, detail)
        return passed

    def record_warn(self, name: str, detail: str) -> None:
        """Record a known environmental limitation — visible in the report but not a failure."""
        self.checks.append({"name": name, "state": WARN, "detail": detail})
        log.warning("%s %s: %s", _ICONS[WARN], name, detail)

    # ── Transaction safety ─────────────────────────────────────────────────────

    def _rollback(self) -> None:
        """Roll back any aborted PostgreSQL transaction so the session stays usable."""
        try:
            self.db.rollback()
        except Exception:
            pass  # nothing to roll back, or session already closed

    # ── Step 1: Schema ─────────────────────────────────────────────────────────

    def check_schema(self) -> None:
        log.info("── Step 1: Schema integrity ──────────────────────────────────────")
        inspector = sa_inspect(engine)

        for table, expected in EXPECTED_COLUMNS.items():
            actual = {c["name"] for c in inspector.get_columns(table)}
            missing = expected - actual
            if missing:
                self.record(
                    f"Schema · {table}",
                    False,
                    f"Missing columns: {sorted(missing)}",
                )
            else:
                extra = actual - expected
                extra_note = f" (extra columns present: {sorted(extra)})" if extra else ""
                self.record(
                    f"Schema · {table}",
                    True,
                    f"All {len(expected)} expected columns present{extra_note}",
                )

    # ── Step 2: Reddit ingest ──────────────────────────────────────────────────

    def run_reddit_ingest(self) -> None:
        log.info("── Step 2: Reddit ingest ─────────────────────────────────────────")

        # Snapshot source PKs before we touch anything
        self.pre_existing_source_pks = {
            row[0] for row in self.db.query(Source.id).all()
        }
        log.info("Pre-existing sources in DB: %d", len(self.pre_existing_source_pks))

        try:
            saved = save_reddit_recipes(self.db, subreddits=["recipes"], limit=5)
            self.inserted_platform_ids.extend(r.source_id for r in saved)

            self.record(
                "Reddit · rows written",
                len(saved) >= 1,
                f"{len(saved)} new recipe(s) inserted from r/recipes (limit=5)",
            )

            if saved:
                sample = saved[0]
                self.record(
                    "Reddit · engagement_score set",
                    sample.engagement_score is not None,
                    f"First row engagement_score = {sample.engagement_score}",
                )
                self.record(
                    "Reddit · content_length > 0",
                    (sample.content_length or 0) > 0,
                    f"First row content_length = {sample.content_length}",
                )
            else:
                log.warning(
                    "No new Reddit rows inserted — all 5 posts may already be in the DB. "
                    "FK and scoring checks will still run against existing data."
                )

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                # GitHub-hosted runners are frequently blocked by Reddit's CDN.
                # This is a known environmental limitation, not a code defect.
                self.reddit_blocked = True
                self.record_warn(
                    "Reddit · ingest",
                    f"Skipped — Reddit returned 403 (runner IP blocked by CDN). "
                    f"Re-run from a non-Actions environment to verify.",
                )
                self._rollback()
            else:
                self.record("Reddit · ingest", False, f"HTTP {exc.response.status_code}: {exc}")
                self._rollback()
                log.exception("Reddit ingest raised an unexpected HTTP error")

        except Exception as exc:
            self.record("Reddit · ingest", False, f"Exception: {exc}")
            self._rollback()
            log.exception("Reddit ingest raised an exception")

    # ── Step 3: TheMealDB ingest ───────────────────────────────────────────────

    def run_themealdb_ingest(self) -> None:
        log.info("── Step 3: TheMealDB ingest ──────────────────────────────────────")
        try:
            saved = save_themealdb_recipes(self.db, queries=["chicken"], max_results=3)
            self.inserted_platform_ids.extend(r.source_id for r in saved)

            self.record(
                "TheMealDB · rows written",
                len(saved) >= 1,
                f"{len(saved)} new recipe(s) inserted (max_results=3)",
            )

            if saved:
                sample = saved[0]
                self.record(
                    "TheMealDB · content_length > 0",
                    (sample.content_length or 0) > 0,
                    f"First row content_length = {sample.content_length}",
                )

        except Exception as exc:
            self.record("TheMealDB · ingest", False, f"Exception: {exc}")
            self._rollback()
            log.exception("TheMealDB ingest raised an exception")

    # ── Step 4: YouTube ingest ─────────────────────────────────────────────────

    def run_youtube_ingest(self) -> None:
        if self.skip_youtube:
            log.info("── Step 4: YouTube ingest (SKIPPED) ─────────────────────────────")
            self.record_warn("YouTube · ingest", "Skipped — SKIP_YOUTUBE=true or no API key")
            return

        log.info("── Step 4: YouTube ingest ────────────────────────────────────────")
        try:
            saved = save_youtube_recipes(self.db, queries=["easy recipe"], max_results=3)
            self.inserted_platform_ids.extend(r.source_id for r in saved)

            self.record(
                "YouTube · rows written",
                len(saved) >= 1,
                f"{len(saved)} new recipe(s) inserted (max_results=3)",
            )

            if saved:
                sample = saved[0]
                self.record(
                    "YouTube · has_transcript set",
                    sample.has_transcript is not None,
                    f"First row has_transcript = {sample.has_transcript}",
                )
                self.record(
                    "YouTube · content_length > 0",
                    (sample.content_length or 0) > 0,
                    f"First row content_length = {sample.content_length}",
                )

        except Exception as exc:
            exc_str = str(exc)
            # youtube-transcript-api surfaces Google 429s as a plain exception whose
            # message contains "Too Many Requests" (HTTP 429).  GitHub runner IPs
            # are frequently throttled by Google, same as Reddit's CDN 403.
            if "429" in exc_str or "Too Many Requests" in exc_str:
                self.record_warn(
                    "YouTube · ingest",
                    "Skipped — YouTube transcript API returned 429 (runner IP rate-limited). "
                    "Re-run from a non-Actions environment to verify.",
                )
            else:
                self.record("YouTube · ingest", False, f"Exception: {exc}")
                log.exception("YouTube ingest raised an exception")
            self._rollback()

    # ── Step 5: FK integrity ───────────────────────────────────────────────────

    def check_fk_integrity(self) -> None:
        log.info("── Step 5: FK integrity ──────────────────────────────────────────")

        if not self.inserted_platform_ids:
            self.record_warn(
                "FK · source_fk non-NULL",
                "No rows were inserted (all connectors blocked or skipped) — "
                "FK check cannot run",
            )
            return

        total = len(self.inserted_platform_ids)
        null_fk_count = (
            self.db.query(RawRecipe)
            .filter(
                RawRecipe.source_id.in_(self.inserted_platform_ids),
                RawRecipe.source_fk.is_(None),
            )
            .count()
        )
        self.record(
            "FK · source_fk non-NULL",
            null_fk_count == 0,
            f"{total - null_fk_count}/{total} inserted row(s) have source_fk set",
        )

    # ── Step 6: Quality scoring ────────────────────────────────────────────────

    def check_scoring(self) -> None:
        log.info("── Step 6: Quality scoring ───────────────────────────────────────")

        try:
            updated = recompute_source_scores(self.db)

            # 0 updated sources is only expected when no rows were inserted at all.
            # YouTube sources score via engagement_score from the statistics API call.
            # TheMealDB sources score via compute_themealdb_completeness() (ingredient count + instruction length).
            if len(updated) == 0 and not self.inserted_platform_ids:
                self.record_warn(
                    "Scoring · sources rescored",
                    "0 sources scored — no rows were inserted (all connectors blocked or skipped). "
                    "Not a code defect.",
                )
                return

            by_platform: dict[str, int] = {}
            for s in updated:
                by_platform[s.platform] = by_platform.get(s.platform, 0) + 1
            platform_summary = ", ".join(f"{v} {k}" for k, v in sorted(by_platform.items()))

            self.record(
                "Scoring · sources rescored",
                len(updated) > 0,
                f"{len(updated)} source(s) updated ({platform_summary})",
            )

            scored_sample = next((s for s in updated if s.quality_score is not None), None)
            if scored_sample:
                in_range = 0.0 <= (scored_sample.quality_score or 0) <= 1.0
                self.record(
                    "Scoring · score in 0.0–1.0 range",
                    in_range,
                    f"{scored_sample.display_name!r} quality_score = {scored_sample.quality_score}",
                )

        except Exception as exc:
            self.record("Scoring · recompute", False, f"Exception: {exc}")
            self._rollback()
            log.exception("Scoring check raised an exception")

    # ── Teardown ───────────────────────────────────────────────────────────────

    def teardown(self) -> None:
        log.info("── Teardown ──────────────────────────────────────────────────────")

        # Clear any aborted transaction before we try to delete rows
        self._rollback()

        if not self.inserted_platform_ids:
            log.info("Nothing to clean up.")
            return

        try:
            # Fetch the DB PKs and source FKs of every recipe we inserted
            recipe_rows = (
                self.db.query(RawRecipe.id, RawRecipe.source_fk)
                .filter(RawRecipe.source_id.in_(self.inserted_platform_ids))
                .all()
            )
            recipe_db_ids = [r.id for r in recipe_rows]
            referenced_source_pks = {r.source_fk for r in recipe_rows if r.source_fk is not None}

            # Sources safe to delete: only those this test created, not pre-existing ones
            new_source_pks = referenced_source_pks - self.pre_existing_source_pks

            # Delete recipes first (FK constraint)
            deleted_recipes = (
                self.db.query(RawRecipe)
                .filter(RawRecipe.id.in_(recipe_db_ids))
                .delete(synchronize_session=False)
            )

            # Delete sources this test created
            deleted_sources = 0
            if new_source_pks:
                deleted_sources = (
                    self.db.query(Source)
                    .filter(Source.id.in_(new_source_pks))
                    .delete(synchronize_session=False)
                )

            self.db.commit()
            log.info(
                "Cleanup complete: %d recipe(s) deleted, %d source(s) deleted.",
                deleted_recipes,
                deleted_sources,
            )

        except Exception:
            log.exception("Teardown failed — some test rows may remain in the database")
            self._rollback()

    # ── Report ─────────────────────────────────────────────────────────────────

    def write_report(self) -> bool:
        n_pass = sum(1 for c in self.checks if c["state"] == PASS)
        n_fail = sum(1 for c in self.checks if c["state"] == FAIL)
        n_warn = sum(1 for c in self.checks if c["state"] == WARN)
        overall_ok = n_fail == 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if overall_ok:
            overall_label = "✅ All checks passed" + (f" ({n_warn} warning(s))" if n_warn else "")
        else:
            overall_label = f"❌ {n_fail} check(s) failed"

        summary_parts = [f"{n_pass} passed", f"{n_fail} failed"]
        if n_warn:
            summary_parts.append(f"{n_warn} warned")
        summary_parts.append(f"{len(self.checks)} total")

        lines = [
            "# Phase 1 — Production Smoke Test Report",
            "",
            f"**Run at:** {now}  ",
            f"**Result:** {overall_label}  ",
            f"**Checks:** {' · '.join(summary_parts)}",
            "",
            "## Check Results",
            "",
            "| Check | Result | Detail |",
            "|-------|:------:|--------|",
        ]
        for c in self.checks:
            icon = _ICONS[c["state"]]
            # Escape any pipe characters in the detail text
            detail = c["detail"].replace("|", "\\|")
            lines.append(f"| {c['name']} | {icon} | {detail} |")

        if n_warn:
            lines += [
                "",
                "> **Note:** ⚠️ warnings indicate known environmental limitations "
                "(e.g. Reddit CDN blocks on GitHub-hosted runners). "
                "They do not indicate a code defect.",
            ]

        lines += [
            "",
            "---",
            "*Generated by `scripts/smoke_test.py`*",
        ]

        report = "\n".join(lines)
        REPORT_PATH.write_text(report, encoding="utf-8")
        log.info("Report written to %s", REPORT_PATH)

        # Also print to stdout so the raw log captures it
        log.info("\n%s", report)

        return overall_ok

    # ── Entrypoint ─────────────────────────────────────────────────────────────

    def run(self) -> bool:
        log.info("=" * 66)
        log.info("Phase 1  Production Smoke Test")
        log.info("=" * 66)
        try:
            self.check_schema()
            self.run_reddit_ingest()
            self.run_themealdb_ingest()
            self.run_youtube_ingest()
            self.check_fk_integrity()
            self.check_scoring()
        finally:
            self.teardown()

        return self.write_report()


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> int:
    skip_youtube = os.getenv("SKIP_YOUTUBE", "false").lower() == "true"

    if not settings.youtube_api_key:
        log.info("YOUTUBE_API_KEY not set — YouTube ingest check will be skipped.")
        skip_youtube = True

    db = SessionLocal()
    try:
        runner = SmokeTestRunner(db, skip_youtube=skip_youtube)
        passed = runner.run()
        return 0 if passed else 1
    except Exception:
        log.exception("Smoke test crashed with an unhandled exception")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

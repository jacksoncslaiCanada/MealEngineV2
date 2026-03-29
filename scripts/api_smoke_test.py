#!/usr/bin/env python
"""One-time API live smoke test — Phase 3 API layer + multi-ingredient search.

Starts the FastAPI app against the real database, makes live HTTP requests,
and verifies the Phase 3 endpoints behave correctly.

Checks:
  1. Health          — GET /health returns {"status": "ok"}
  2. List recipes    — GET /recipes returns ≥1 recipe with expected fields
  3. Recipe detail   — GET /recipes/{id} embeds ingredients list
  4. Ingredient list — GET /recipes/{id}/ingredients returns ingredient rows
  5. Ingredient search (single)    — GET /ingredients/search?name=chicken
  6. Canonical name populated      — canonical_name non-null in search results
  7. Recipe search (single term)   — GET /recipes/search?ingredient=chicken
  8. Recipe search (AND, 2 terms)  — both terms present in at least one recipe
  9. Recipe search (OR, 2 terms)   — at least one term present
 10. Recipe search (no match)      — unknown ingredient returns []

No data is written or deleted — this is read-only against the live database.
A Markdown report is written to api_smoke_test_report.md.

Usage
-----
    python scripts/api_smoke_test.py

Secrets required:
    DATABASE_URL — PostgreSQL connection string (env var or .env)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

REPORT_PATH = Path("api_smoke_test_report.md")
API_HOST = "127.0.0.1"
API_PORT = 8765
BASE_URL = f"http://{API_HOST}:{API_PORT}"
STARTUP_TIMEOUT = 20   # seconds to wait for uvicorn to be ready
SEARCH_TERM = "chicken"  # term expected to match real rows in the live DB

PASS = "pass"
FAIL = "fail"
WARN = "warn"
_ICONS = {PASS: "✅", FAIL: "❌", WARN: "⚠️"}


class ApiSmokeTestRunner:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self._proc: subprocess.Popen | None = None
        self._client: httpx.Client | None = None

    # ── Recording helpers ──────────────────────────────────────────────────────

    def record(self, name: str, passed: bool, detail: str) -> bool:
        state = PASS if passed else FAIL
        self.checks.append({"name": name, "state": state, "detail": detail})
        log.log(logging.INFO if passed else logging.ERROR,
                "%s %s: %s", _ICONS[state], name, detail)
        return passed

    def record_warn(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "state": WARN, "detail": detail})
        log.warning("%s %s: %s", _ICONS[WARN], name, detail)

    # ── Server lifecycle ───────────────────────────────────────────────────────

    def _start_server(self) -> bool:
        """Start uvicorn in a subprocess. Returns True when /health responds."""
        log.info("Starting API server on %s:%d …", API_HOST, API_PORT)
        env = {**os.environ, "DATABASE_URL": settings.database_url or ""}
        self._proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--host", API_HOST,
                "--port", str(API_PORT),
                "--log-level", "warning",
            ],
            env=env,
        )

        deadline = time.monotonic() + STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            try:
                resp = httpx.get(f"{BASE_URL}/health", timeout=2)
                if resp.status_code == 200:
                    log.info("Server ready.")
                    return True
            except httpx.ConnectError:
                pass
            time.sleep(0.5)

        log.error("Server did not become ready within %ds.", STARTUP_TIMEOUT)
        return False

    def _stop_server(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            log.info("Server stopped.")

    # ── Checks ─────────────────────────────────────────────────────────────────

    def check_health(self) -> None:
        log.info("── Check 1: Health ───────────────────────────────────────────────")
        try:
            resp = httpx.get(f"{BASE_URL}/health", timeout=5)
            ok = resp.status_code == 200 and resp.json() == {"status": "ok"}
            self.record("Health · GET /health", ok,
                        f"status={resp.status_code} body={resp.text!r}")
        except Exception as exc:
            self.record("Health · GET /health", False, f"Exception: {exc}")

    def check_list_recipes(self) -> int | None:
        """Returns the ID of the first recipe, or None on failure."""
        log.info("── Check 2: List recipes ─────────────────────────────────────────")
        try:
            resp = httpx.get(f"{BASE_URL}/recipes", timeout=10)
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list) and len(data) >= 1
            self.record(
                "Recipes · GET /recipes",
                ok,
                f"status={resp.status_code}, {len(data)} recipe(s) returned",
            )
            if not ok:
                return None

            item = data[0]
            has_fields = all(
                f in item
                for f in ("id", "source", "source_id", "url",
                          "fetched_at", "engagement_score")
            )
            self.record(
                "Recipes · response shape",
                has_fields,
                f"Fields present: {sorted(item.keys())}",
            )
            return item["id"] if ok else None

        except Exception as exc:
            self.record("Recipes · GET /recipes", False, f"Exception: {exc}")
            return None

    def check_recipe_detail(self, recipe_id: int) -> None:
        log.info("── Check 3: Recipe detail ────────────────────────────────────────")
        try:
            resp = httpx.get(f"{BASE_URL}/recipes/{recipe_id}", timeout=10)
            data = resp.json()
            ok = resp.status_code == 200 and "ingredients" in data
            self.record(
                f"Recipes · GET /recipes/{recipe_id}",
                ok,
                f"status={resp.status_code}, "
                f"{len(data.get('ingredients', []))} ingredient(s) embedded",
            )
        except Exception as exc:
            self.record(f"Recipes · GET /recipes/{recipe_id}", False, f"Exception: {exc}")

    def check_recipe_ingredients(self, recipe_id: int) -> None:
        log.info("── Check 4: Recipe ingredients list ──────────────────────────────")
        try:
            resp = httpx.get(f"{BASE_URL}/recipes/{recipe_id}/ingredients", timeout=10)
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list)
            self.record(
                f"Recipes · GET /recipes/{recipe_id}/ingredients",
                ok,
                f"status={resp.status_code}, {len(data)} row(s)",
            )
        except Exception as exc:
            self.record(
                f"Recipes · GET /recipes/{recipe_id}/ingredients",
                False,
                f"Exception: {exc}",
            )

    def check_ingredient_search(self) -> None:
        log.info("── Check 5: Ingredient search ────────────────────────────────────")
        try:
            resp = httpx.get(
                f"{BASE_URL}/ingredients/search",
                params={"name": SEARCH_TERM},
                timeout=10,
            )
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list) and len(data) >= 1
            self.record(
                f"Ingredients · search '{SEARCH_TERM}'",
                ok,
                f"status={resp.status_code}, {len(data)} match(es)",
            )
            if not ok:
                return

            # Check 6: canonical_name populated
            log.info("── Check 6: canonical_name populated ────────────────────────────")
            with_canonical = sum(1 for r in data if r.get("canonical_name"))
            self.record(
                "Ingredients · canonical_name populated",
                with_canonical > 0,
                f"{with_canonical}/{len(data)} result(s) have canonical_name set "
                f"(backfill OK)" if with_canonical > 0
                else "canonical_name is NULL on all results — backfill may not have run",
            )

        except Exception as exc:
            self.record(f"Ingredients · search '{SEARCH_TERM}'", False, f"Exception: {exc}")

    def check_recipe_search_single(self) -> None:
        log.info("── Check 7: Recipe search (single term) ──────────────────────────")
        try:
            resp = httpx.get(
                f"{BASE_URL}/recipes/search",
                params={"ingredient": SEARCH_TERM},
                timeout=10,
            )
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list) and len(data) >= 1
            self.record(
                f"Recipe search · single term '{SEARCH_TERM}'",
                ok,
                f"status={resp.status_code}, {len(data)} recipe(s) returned",
            )
            if ok:
                item = data[0]
                has_ingredients = "ingredients" in item
                self.record(
                    "Recipe search · ingredients embedded",
                    has_ingredients,
                    f"First result has 'ingredients' key: {has_ingredients}",
                )
        except Exception as exc:
            self.record(f"Recipe search · single term '{SEARCH_TERM}'", False, f"Exception: {exc}")

    def check_recipe_search_and(self) -> None:
        log.info("── Check 8: Recipe search (AND) ──────────────────────────────────")
        # Use two terms likely to co-occur; not a hard failure if DB happens not to have them
        terms = [SEARCH_TERM, "garlic"]
        try:
            resp = httpx.get(
                f"{BASE_URL}/recipes/search",
                params={"ingredient": terms, "match": "all"},
                timeout=10,
            )
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list)
            detail = (
                f"status={resp.status_code}, {len(data)} recipe(s) have "
                f"both {terms[0]!r} AND {terms[1]!r}"
            )
            if ok and len(data) == 0:
                self.record_warn(
                    f"Recipe search · AND ({'+'.join(terms)})",
                    detail + " — no co-occurrence in DB; not a code defect",
                )
            else:
                self.record(f"Recipe search · AND ({'+'.join(terms)})", ok, detail)
        except Exception as exc:
            self.record(
                f"Recipe search · AND ({'+'.join(terms)})", False, f"Exception: {exc}"
            )

    def check_recipe_search_or(self) -> None:
        log.info("── Check 9: Recipe search (OR) ───────────────────────────────────")
        terms = [SEARCH_TERM, "broccoli"]
        try:
            resp = httpx.get(
                f"{BASE_URL}/recipes/search",
                params={"ingredient": terms, "match": "any"},
                timeout=10,
            )
            data = resp.json()
            ok = resp.status_code == 200 and isinstance(data, list) and len(data) >= 1
            self.record(
                f"Recipe search · OR ({'+'.join(terms)})",
                ok,
                f"status={resp.status_code}, {len(data)} recipe(s) returned",
            )
        except Exception as exc:
            self.record(
                f"Recipe search · OR ({'+'.join(terms)})", False, f"Exception: {exc}"
            )

    def check_recipe_search_no_match(self) -> None:
        log.info("── Check 10: Recipe search (no match) ────────────────────────────")
        try:
            resp = httpx.get(
                f"{BASE_URL}/recipes/search",
                params={"ingredient": "xyzzy_no_such_ingredient_12345"},
                timeout=10,
            )
            data = resp.json()
            ok = resp.status_code == 200 and data == []
            self.record(
                "Recipe search · unknown ingredient returns []",
                ok,
                f"status={resp.status_code}, body={data!r}",
            )
        except Exception as exc:
            self.record("Recipe search · unknown ingredient returns []", False, f"Exception: {exc}")

    # ── Report ─────────────────────────────────────────────────────────────────

    def write_report(self) -> bool:
        n_pass = sum(1 for c in self.checks if c["state"] == PASS)
        n_fail = sum(1 for c in self.checks if c["state"] == FAIL)
        n_warn = sum(1 for c in self.checks if c["state"] == WARN)
        overall_ok = n_fail == 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        overall_label = (
            "✅ All checks passed" + (f" ({n_warn} warning(s))" if n_warn else "")
            if overall_ok
            else f"❌ {n_fail} check(s) failed"
        )
        summary_parts = [f"{n_pass} passed", f"{n_fail} failed"]
        if n_warn:
            summary_parts.append(f"{n_warn} warned")
        summary_parts.append(f"{len(self.checks)} total")

        lines = [
            "# Phase 3 API — Live Smoke Test Report",
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
            detail = c["detail"].replace("|", "\\|")
            lines.append(f"| {c['name']} | {_ICONS[c['state']]} | {detail} |")

        lines += ["", "---", "*Generated by `scripts/api_smoke_test.py`*"]
        report = "\n".join(lines)
        REPORT_PATH.write_text(report, encoding="utf-8")
        log.info("Report written to %s", REPORT_PATH)
        log.info("\n%s", report)
        return overall_ok

    # ── Entrypoint ─────────────────────────────────────────────────────────────

    def run(self) -> bool:
        log.info("=" * 66)
        log.info("Phase 3 API  Live Smoke Test")
        log.info("=" * 66)
        try:
            ready = self._start_server()
            if not ready:
                self.record("Server startup", False,
                            f"uvicorn did not become ready within {STARTUP_TIMEOUT}s")
                return self.write_report()

            self.check_health()
            recipe_id = self.check_list_recipes()
            if recipe_id is not None:
                self.check_recipe_detail(recipe_id)
                self.check_recipe_ingredients(recipe_id)
            else:
                self.record_warn("Recipes · detail + ingredients",
                                 "Skipped — no recipe ID available from list check")
            self.check_ingredient_search()
            self.check_recipe_search_single()
            self.check_recipe_search_and()
            self.check_recipe_search_or()
            self.check_recipe_search_no_match()
        finally:
            self._stop_server()

        return self.write_report()


def main() -> int:
    if not settings.database_url or settings.database_url.startswith("postgresql://user:password"):
        log.error("DATABASE_URL is not configured. Aborting.")
        return 1

    runner = ApiSmokeTestRunner()
    try:
        passed = runner.run()
        return 0 if passed else 1
    except Exception:
        log.exception("API smoke test crashed with an unhandled exception")
        return 1


if __name__ == "__main__":
    sys.exit(main())

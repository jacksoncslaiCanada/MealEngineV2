# MealEngineV2 — Implementation Plan & Current State

## Stack
- **Backend:** Python 3.11 + FastAPI
- **Database:** PostgreSQL (hosted externally; `DATABASE_URL` secret)
- **Ingredient Extraction:** Anthropic Claude API
- **Frontend:** Bootstrap 5.3 + Vanilla JS, served by FastAPI (Jinja2 templates)
- **Hosting:** Railway.app (auto-deploys from `main` branch)
- **CI/CD:** GitHub Actions

---

## Phase 1 — Recipe Source Connectors ✅ Done

**Goal:** Reliably pull raw recipe data from Reddit, YouTube, and TheMealDB.

### What was built
- `app/connectors/reddit.py` — Reddit public JSON API; fetches hot posts from tracked subreddits; computes engagement score from upvotes + ratio
- `app/connectors/youtube.py` — YouTube Data API v3; fetches video metadata + transcripts via `youtube-transcript-api`; computes engagement score from views + likes
- `app/connectors/themealdb.py` — TheMealDB REST API; no credentials required; uses ingredient count + instruction length for engagement score
- `app/db/models.py` — `Source`, `RawRecipe`, `Ingredient` ORM models
- `app/schemas.py` — Pydantic schemas for ingest-layer data shapes
- 9 Alembic migrations covering full schema history

### Tests
- `tests/test_reddit.py`, `tests/test_youtube.py`, `tests/test_themealdb.py` — connector unit tests with mocked responses
- `tests/test_integration.py` — live fetch integration tests using fixtures

**Gate:** ✅ Raw data from all three sources lands in the DB reliably.

---

## Phase 1.5 — Source Registry & Scoring ✅ Done

**Goal:** Make sources managed entities with lifecycle tracking, quality scoring, and automatic discovery of new candidates.

### What was built
- **1.5a** — `sources` table + migrations; engagement signal columns on `raw_recipes`; `app/scoring.py` with:
  - `compute_reddit_engagement()`, `compute_youtube_engagement()`, `compute_themealdb_completeness()`
  - `compute_completeness_bonus()` — 0–20 pt bonus for recipes with ≥5 structured ingredients
  - `recompute_source_scores()` — recency-weighted average with completeness bonus applied
  - `auto_promote_candidates()`, `get_or_create_source()`, `mark_source_ingested()`
- **1.5b** — `app/discovery.py`: Reddit author cross-posting sweep + keyword search; YouTube channel extraction with video count and engagement gating
- **1.5c** — `app/pipeline.py`: 5-step weekly pipeline (ingest → extract → score → discover → promote); `scripts/run_pipeline.py`; `weekly_pipeline.yml` (Sunday 08:00 UTC, manual trigger)

### Tests
- `tests/test_scoring.py` — 37 tests: engagement formulas, completeness bonus, source scoring, auto-promotion
- `tests/test_discovery.py` — discovery sweep unit tests
- `tests/test_pipeline.py` — pipeline orchestration and error handling

**Gate:** ✅ Weekly run ingests from all active sources, scores them, discovers candidates, and produces a summary without manual intervention.

---

## Phase 2 — Ingredient Extraction ✅ Done

**Goal:** Parse raw recipe content into structured ingredients using Claude.

### What was built
- `app/extractor.py` — calls Claude API with forced tool use; deduplicates by `source_id`; skips recipes without transcripts; sets `canonical_name` at extraction time
- `app/normaliser.py` — `normalise_ingredient()`: strips prep prefixes (`diced`, `chopped`, `fresh`…), trailing cut/form words (`thighs`, `cloves`, `fillets`…), synonym map (cilantro→coriander, bell pepper→pepper, plain flour→flour…), simple pluralisation
- `alembic/versions/b7c8d9e0f1a2` — adds `canonical_name` column + index to `ingredients`
- `scripts/run_extraction.py` — standalone extraction runner
- `scripts/backfill_canonical_names.py` — one-time backfill (ran 2026-03-29; 94 rows updated)

### Tests
- `tests/test_extractor.py` — unit tests with mocked Anthropic API
- `tests/test_extractor_accuracy.py` — accuracy test vs. ground truth fixtures (155/155 recall, 100%)
- `tests/test_normaliser.py` — 50 parametrised unit tests

**Production results:** 26 unprocessed recipes → 45 ingredients extracted in a single pipeline run; 94 existing rows backfilled with `canonical_name`.

**Gate:** ✅ Extraction hits accuracy threshold; `canonical_name` populated on all ingredient rows.

---

## Phase 3 — API Layer + Normalisation + Quality Signal ✅ Done

**Goal:** Expose recipe and ingredient data via a clean REST API; normalise ingredient names; feed extraction quality back into source scoring.

### What was built

**Step 1 — FastAPI routes**
- `app/main.py` — FastAPI app; mounts `/static`; includes all routers; `/` redirects to `/ui/meal-plan`
- `app/routes/recipes.py`:
  - `GET /recipes` — list with optional `?source=` filter, pagination
  - `GET /recipes/{id}` — detail with ingredients embedded
  - `GET /recipes/{id}/ingredients` — ingredient list
  - `GET /recipes/search?ingredient=X&ingredient=Y&match=all|any` — multi-ingredient AND/OR search
  - `GET /recipes/meal-plan?ingredient=X&min_coverage=0.5` — pantry-based recipe finder
- `app/routes/ingredients.py`:
  - `GET /ingredients/search?name=X` — searches `ingredient_name` and `canonical_name`
- `app/routes/schemas.py` — `IngredientOut`, `RecipeOut`, `RecipeDetailOut`, `IngredientSearchResult`, `MealPlanResult`
- `GET /health` → `{"status": "ok"}`

**Step 2 — Normalisation**
(See Phase 2 — `app/normaliser.py` built and wired here)

**Step 3 — Quality signal**
`compute_completeness_bonus()` in `app/scoring.py` adds up to 20 pts to a recipe's effective engagement score when ≥5 structured ingredients are present. Applied inside `recompute_source_scores()`.

### Tests
- `tests/test_api.py` — 48 tests covering all endpoints (TestClient + SQLite StaticPool)
- `tests/test_normaliser.py` — 50 normaliser unit tests
- `tests/test_scoring.py` — 37 scoring tests including completeness bonus

### Live smoke test
- `scripts/api_smoke_test.py` — 15 live checks against running API (health, recipes, ingredients, recipe search AND/OR, meal plan coverage)
- `.github/workflows/api_smoke_test.yml` — permanent manual workflow; run after any API change

**Gate:** ✅ All 141 unit tests pass; 15/15 live API smoke test checks pass.

---

## Phase 4 — Frontend & More Sources (In Progress)

### Item 1 — Backfill `canonical_name` ✅ Done
One-time script + workflow ran 2026-03-29; 94 rows updated; workflow deleted.

### Item 2 — Multi-ingredient recipe search ✅ Done
`GET /recipes/search?ingredient=chicken&ingredient=garlic&match=all`

### Item 3 — Meal planning endpoint ✅ Done
`GET /recipes/meal-plan?ingredient=chicken&ingredient=garlic&min_coverage=0.5`
Returns recipes scored by coverage (matched ingredients / total ingredients), sorted descending.

### Item 4 — Frontend (Meal Planner) ✅ Done
- `app/templates/base.html` — Bootstrap 5.3 shell; dark navbar; tag-input CSS; source badge styles
- `app/templates/meal_plan.html` — Meal Planner page; tag-style ingredient input; coverage slider
- `app/static/meal_plan.js` — tag input (Enter/comma/backspace); fetch `/recipes/meal-plan`; recipe cards with Bootstrap progress bar and collapsible ingredient pills (✅ matched / ➖ missing)
- `app/routes/ui.py` — `/ui` redirect + `/ui/meal-plan` Jinja2 template route
- Navbar has commented slot ready for Recipe Browser and Ingredient Search views
- Deployed at Railway; `railway.toml` + `.python-version` (3.11) in repo

### Item 5 — More sources ✅ Done

**Goal:** Add more recipe variety without breaking existing pipeline.

#### What was built
- **Maangchi (YouTube)** — added `"maangchi korean recipe"` to `RECIPE_SEARCH_QUERIES` in `app/connectors/youtube.py`; captured by the existing query-based YouTube ingest.
- **TheMealDB (pipeline)** — `save_themealdb_recipes` wired into Step 1 of the weekly pipeline; already had good queries (`chicken`, `pasta`, `beef`, `salmon`); free API, no credentials.
- **Woks of Life (RSS)** — `app/connectors/rss.py`:
  - Uses `feedparser` to pull the `https://thewoksoflife.com/feed/` Atom/RSS feed
  - `platform="rss"`, `handle` derived from feed domain (e.g. `thewoksoflife.com`)
  - Engagement score: content length / 100, capped at 80
  - `has_transcript=False`; deduplication by entry `id` (or SHA-256 of link)
  - `save_rss_recipes()` follows the same get-or-create-source / mark-ingested pattern as other connectors
- **`PipelineReport`** — added `themealdb_new: int = 0` and `rss_new: int = 0`; `total_new` sums all four sources; log output updated.
- **`app/schemas.py`** — `RawRecipeSchema.source` literal extended with `"rss"`.
- **`requirements.txt`** — added `feedparser==6.0.11`.

#### Tests
- `tests/test_rss.py` — 24 unit tests (entry ID, content extraction, handle derivation, fetch, save, dedup, engagement cap)
- `tests/test_pipeline.py` — `autouse` fixture patches TheMealDB + RSS; new `test_pipeline_report_themealdb_and_rss_counts` test; renamed `test_pipeline_calls_all_steps`

**Total tests: 256 passed.**

#### Backlog (from this item)
| Item | Notes |
|------|-------|
| Serious Eats / BBC Good Food RSS | Option A: full article fetch; Option B: summary only |

---

## Backlog

| Item | Notes |
|------|-------|
| ⚠️ **Add API key auth before going public** | API is fully open. Add `X-API-Key` header check in FastAPI middleware before sharing the Railway URL widely. |
| Recipe Browser view (`/ui/recipes`) | List/filter all recipes; nav slot already present in `base.html` |
| Ingredient Search view (`/ui/search`) | Single search box → matching recipes; nav slot already present |
| Serious Eats / BBC Good Food RSS | Option A: full article page fetch; Option B: summary-only from RSS |

---

## Repository Layout

```
app/
  connectors/        reddit.py · youtube.py · themealdb.py · rss.py
  db/                base.py · session.py · models.py
  routes/            recipes.py · ingredients.py · ui.py · schemas.py
  static/            meal_plan.js
  templates/         base.html · meal_plan.html
  config.py · main.py · pipeline.py · discovery.py
  extractor.py · normaliser.py · scoring.py · schemas.py

alembic/versions/    9 migrations (full schema history)

scripts/
  run_pipeline.py          CLI entry point for weekly pipeline
  run_extraction.py        Standalone extraction runner
  smoke_test.py            Phase 1+2 production smoke test (7 checks)
  api_smoke_test.py        Phase 3+ API live smoke test (15 checks)
  backfill_canonical_names.py  One-time utility (completed)

tests/               12 test modules · 256 tests total

.github/workflows/
  test.yml              Unit tests on push/PR
  integration.yml       Integration tests
  smoke_test.yml        Phase 1+2 smoke test (manual)
  api_smoke_test.yml    Phase 3+ API smoke test (manual)
  extract_ingredients.yml  Standalone extraction run
  weekly_pipeline.yml   Full pipeline (Sunday 08:00 UTC + manual)

railway.toml          Railway deployment config
.python-version       Pins Python 3.11
requirements.txt      All dependencies
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Ingredient matching | `ingredient_name` + `canonical_name` ilike OR | Handles spelling variants and prep-word noise |
| Source scoring | Recency-weighted avg + completeness bonus | Rewards sources with well-structured recipes |
| Extraction dedup | Skip if `Ingredient` rows already exist for `recipe_id` | Idempotent pipeline runs |
| API tests | SQLite StaticPool in-memory | No Postgres needed in CI; all connections share one DB |
| Frontend serving | FastAPI StaticFiles + Jinja2 | No separate server; same repo and deployment |
| Collapse toggle | Vanilla JS `.classList.toggle('show')` | Bootstrap JS global unreliable on Railway CDN |

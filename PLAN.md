# MealEngineV2 — Implementation Plan & Current State

_Last updated: 2026-04-02_

## Stack
- **Backend:** Python 3.11 + FastAPI
- **Database:** PostgreSQL (hosted on Railway; `DATABASE_URL` secret)
- **Ingredient Extraction:** Anthropic Claude API (claude-opus-4-6, forced tool use)
- **Frontend:** Bootstrap 5.3 + Vanilla JS, served by FastAPI (Jinja2 templates)
- **Hosting:** Railway.app (auto-deploys from `main` branch)
- **CI/CD:** GitHub Actions (6 workflows)

---

## Phase 1 — Recipe Source Connectors ✅ Done

**Goal:** Reliably pull raw recipe data from Reddit, YouTube, and TheMealDB.

### What was built
- `app/connectors/reddit.py` — Reddit public JSON API; fetches hot posts from tracked subreddits; engagement score from upvotes × upvote ratio (log-scaled)
- `app/connectors/youtube.py` — YouTube Data API v3; query-based ingestion (4 search queries); video metadata + transcripts via `youtube-transcript-api`; engagement score from views + likes (log-scaled); `_fetch_statistics` batches IDs in groups of 50 (YouTube API limit)
- `app/connectors/themealdb.py` — TheMealDB REST API (free, no credentials); engagement score from ingredient count + instruction length
- `app/db/models.py` — `Source`, `RawRecipe`, `Ingredient` ORM models
- `app/schemas.py` — Pydantic ingest-layer schemas; `source` literal: `reddit | youtube | themealdb | rss`
- 9 Alembic migrations covering full schema history

### Tests
- `tests/test_reddit.py`, `tests/test_youtube.py`, `tests/test_themealdb.py` — connector unit tests with mocked responses
- `tests/test_integration.py` — live fetch integration tests

**Gate:** ✅ Raw data from all sources lands in the DB reliably.

---

## Phase 1.5 — Source Registry & Scoring ✅ Done

**Goal:** Make sources managed entities with lifecycle tracking, quality scoring, and automatic discovery of new candidates.

### What was built

**Scoring (`app/scoring.py`)**
- `compute_reddit_engagement(score, upvote_ratio)` → 0–100
- `compute_youtube_engagement(views, likes)` → 0–100 (log-scaled)
- `compute_themealdb_completeness(ingredient_count, instruction_length)` → 0–100
- `compute_completeness_bonus(ingredient_count)` → 0–20 bonus pts for recipes with ≥5 structured ingredients
- `recompute_source_scores(db)` — recency-weighted average (window=20, decay=0.9) with completeness bonus applied per recipe
- `auto_promote_candidates(db, threshold, min_content)` — promotes candidates to active when:
  - `quality_score >= threshold` (default **0.75**, raised from 0.6 to reduce noise)
  - `content_count >= min_content` (default **2**, prevents one-run wonders from promoting)
- `get_or_create_source()`, `mark_source_ingested()`

**Discovery (`app/discovery.py`)**
- Reddit: author cross-posting sweep + keyword search
- YouTube: channel extraction from search results; requires `discovery_min_video_count=5` videos before candidacy; computes avg engagement across recent videos

**Pipeline (`app/pipeline.py`)**
5-step weekly pipeline:
1. **Ingest** — Reddit + YouTube + TheMealDB + RSS (each isolated with try/except; errors captured, not fatal)
2. **Extract** — runs `extract_all_unprocessed`; per-recipe error isolation (one failed recipe logs a warning, others continue); `db.rollback()` on session failure so subsequent steps are not poisoned
3. **Score** — `recompute_source_scores`
4. **Discover** — `run_discovery_sweep`
5. **Promote** — `auto_promote_candidates`

`PipelineReport` dataclass: `reddit_new`, `youtube_new`, `themealdb_new`, `rss_new`, `ingredients_extracted`, `sources_rescored`, `discovery`, `promoted`, `elapsed_seconds`, `errors`; `total_new` sums all four sources.

**Scripts & workflows**
- `scripts/run_pipeline.py` — CLI entry point
- `.github/workflows/weekly_pipeline.yml` — Sunday 08:00 UTC + manual dispatch
- `scripts/smoke_test.py` — Phase 1+2 production smoke test (7 checks)

### Tests
- `tests/test_scoring.py` — 39 tests: engagement formulas, completeness bonus, source scoring, auto-promotion (threshold gate + min_content gate)
- `tests/test_discovery.py` — discovery sweep unit tests
- `tests/test_pipeline.py` — orchestration, error handling, active source selection

**Gate:** ✅ Weekly run ingests from all active sources, scores, discovers, promotes — produces a summary without manual intervention.

---

## Phase 2 — Ingredient Extraction ✅ Done

**Goal:** Parse raw recipe content into structured ingredients using Claude.

### What was built
- `app/extractor.py`:
  - `extract_ingredients(db, recipe)` — calls Claude API with forced `record_ingredients` tool use; wraps `db.commit()` in try/except with rollback on failure
  - `extract_all_unprocessed(db)` — per-recipe try/except; one failed recipe logs a warning and continues (does not abort the batch)
- `app/normaliser.py` — `normalise_ingredient()`: strips prep prefixes (`diced`, `chopped`, `fresh`…), trailing cut/form words (`thighs`, `cloves`, `fillets`…), synonym map (cilantro→coriander, bell pepper→pepper, plain flour→flour…), simple pluralisation
- `scripts/backfill_canonical_names.py` — one-time backfill (ran 2026-03-29; 94 rows updated; script retained, workflow deleted)
- `scripts/run_extraction.py` — standalone extraction runner

### Tests
- `tests/test_extractor.py` — unit tests with mocked Anthropic API
- `tests/test_extractor_accuracy.py` — accuracy test vs. ground truth fixtures
- `tests/test_normaliser.py` — 50 parametrised unit tests

**Gate:** ✅ `canonical_name` populated on all ingredient rows; extraction is idempotent.

---

## Phase 3 — API Layer ✅ Done

**Goal:** Expose recipe and ingredient data via a clean REST API.

### What was built

**`app/routes/recipes.py`**
- `GET /recipes/browse` — Recipe Browser endpoint (see Phase 4 Item 6):
  - Params: `q` (keyword), `source`, `min_ingredients`, `sort` (newest|engagement), `limit`, `offset`
  - Returns `RecipeBrowseItem` list with title extracted from `raw_content`, ingredient count via correlated subquery
- `GET /recipes/meal-plan?ingredient=X&min_coverage=0.5` — pantry-based recipe finder; coverage = matched/total; sorted desc
- `GET /recipes/search?ingredient=X&match=all|any` — multi-ingredient AND/OR search on `ingredient_name` + `canonical_name`
- `GET /recipes` — list with optional `?source=` filter, pagination
- `GET /recipes/{id}` — detail with ingredients embedded
- `GET /recipes/{id}/ingredients` — ingredient list

**`app/routes/ingredients.py`**
- `GET /ingredients/search?name=X` — searches `ingredient_name` and `canonical_name`

**`app/routes/schemas.py`**
- `IngredientOut`, `RecipeOut`, `RecipeDetailOut`, `IngredientSearchResult`
- `MealPlanResult(RecipeDetailOut)` — adds `coverage`, `matched_count`, `total_count`
- `RecipeBrowseItem` — adds `title`, `ingredient_count` for the browser UI

**`GET /health`** → `{"status": "ok"}`

### Tests
- `tests/test_api.py` — 48 tests covering all endpoints

### Live smoke test
- `scripts/api_smoke_test.py` — 15 live checks (health, recipes, ingredients, search AND/OR, meal plan)
- `.github/workflows/api_smoke_test.yml` — permanent manual workflow

**Gate:** ✅ All endpoint tests pass; 15/15 live smoke checks pass.

---

## Phase 4 — Frontend & More Sources (In Progress)

### Item 1 — Backfill `canonical_name` ✅ Done
One-time script ran 2026-03-29; 94 rows updated.

### Item 2 — Multi-ingredient recipe search ✅ Done
`GET /recipes/search?ingredient=chicken&ingredient=garlic&match=all`

### Item 3 — Meal planning endpoint ✅ Done
`GET /recipes/meal-plan?ingredient=chicken&ingredient=garlic&min_coverage=0.5`

### Item 4 — Meal Planner UI ✅ Done

**Files:**
- `app/templates/base.html` — Bootstrap 5.3.3 shell; dark navbar; tag-input CSS; source badge styles (YouTube/TheMealDB/Reddit/RSS); coverage bar styles
- `app/templates/meal_plan.html` — tag-style ingredient input; coverage slider (0–100%); results area
- `app/static/meal_plan.js` — tag input with Enter/comma/backspace; fetches `/recipes/meal-plan`; recipe cards with Bootstrap progress bar; collapsible ingredient pills (✅ matched / ➖ missing) via vanilla JS `classList.toggle('show')` (Bootstrap JS global avoided — unreliable on Railway CDN)
- `app/routes/ui.py` — `/ui` redirect + `/ui/meal-plan` + `/ui/recipes` Jinja2 routes
- `app/main.py` — mounts `/static` (StaticFiles); includes `ui_router`; `/` → `RedirectResponse("/ui/meal-plan")`

**Deployment:**
- `railway.toml` — nixpacks builder; `startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"`
- `.python-version` — pins Python 3.11 (Railway default was 3.13 which broke `psycopg2-binary`)
- `requirements.txt` additions: `jinja2==3.1.6`, `python-multipart==0.0.12`

### Item 5 — More Sources ✅ Done

**New connector — `app/connectors/rss.py`:**
- Uses `feedparser` to pull RSS/Atom feeds
- Default feed: `https://thewoksoflife.com/feed/` (Woks of Life)
- `platform="rss"`, `handle` = feed domain without `www.` (e.g. `thewoksoflife.com`)
- Engagement score = `min(content_length / 100, 80.0)` — proxy for article depth
- Deduplication by entry `id` field; falls back to SHA-256 of link
- `save_rss_recipes()` follows get-or-create-source / mark-ingested pattern
- `requirements.txt` — added `feedparser==6.0.11`

**Pipeline additions:**
- TheMealDB wired into Step 1 ingest (was already built, just not called)
- RSS wired into Step 1 ingest
- `PipelineReport` extended with `themealdb_new`, `rss_new`; `total_new` sums all four sources
- YouTube search queries updated: `"recipe"` → `"homemade recipe"` (reduces generic/non-food channels)

**Maangchi (YouTube):** `"maangchi korean recipe"` added to `RECIPE_SEARCH_QUERIES`.

**Tests:** `tests/test_rss.py` — 24 unit tests; `tests/test_pipeline.py` — autouse fixture for new connectors.

### Item 6 — Recipe Browser UI ✅ Done

**Files:**
- `app/templates/recipes.html` — sticky filter sidebar + responsive table; source badges; score bar; relative dates ("3d ago"); external link button
- `app/static/recipes.js` — live filter/search; sort toggle (Newest / Engagement); prev/next pagination in groups of 50; Enter-to-search on keyword input
- `app/templates/base.html` — "Recipes" nav link added (was a commented slot)

**API backing it:**
- `GET /recipes/browse` — `q`, `source`, `min_ingredients`, `sort`, `limit`, `offset`
- Title extracted from first line of `raw_content` (strips `"Title: "` / `"Meal: "` prefix)
- Ingredient count via SQLAlchemy correlated subquery (no extra JOIN overhead)

### Item 7 — Promotion Quality Tightening ✅ Done

Addressed noisy auto-promotions (Hodder Books, OnlyPokemon, Uncle Roger Shorts):

| Change | Before | After | Effect |
|--------|--------|-------|--------|
| `source_quality_threshold` | 0.6 | **0.75** | Requires ~10M+ views/video to direct-promote via discovery |
| `source_promotion_min_content` | — | **2** | Channel must appear in ≥2 pipeline runs before promoting |
| YouTube query `"recipe"` | bare | **`"homemade recipe"`** | Fewer generic channels in search results |

---

## Bug Fixes Applied

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Railway crash (Python 3.13 + libpq) | Railway auto-selected Python 3.13; psycopg2-binary incompatible | Added `.python-version` (3.11) + `railway.toml` |
| Root URL 404 | No route on `/` | `RedirectResponse` from `/` → `/ui/meal-plan` in `app/main.py` |
| Bootstrap collapse broken on dynamic HTML | CDN timing; Bootstrap JS global unavailable | Replaced with vanilla JS `classList.toggle('show')` |
| DB connection timeout killing scoring step | Long Anthropic API retry left Postgres connection idle; `db.commit()` failed; poisoned session propagated | `extract_ingredients`: rollback on commit failure; `extract_all_unprocessed`: per-recipe try/except; `pipeline.py`: `db.rollback()` after extraction error |
| YouTube stats API 400 error | `videos.list` has 50-ID limit; 4 queries × 10 results = 53 unique IDs | `_fetch_statistics` now chunks IDs in batches of 50 |

---

## Backlog

| Item | Priority | Notes |
|------|----------|-------|
| ⚠️ **Add API key auth** | High | API is fully open. Add `X-API-Key` header check in FastAPI middleware before sharing Railway URL widely |
| Serious Eats / BBC Good Food RSS | Medium | Option A: full article page fetch; Option B: summary-only from feed |
| Ingredient Search view (`/ui/search`) | Low | Single search box → matching recipes; could reuse `/recipes/search` API |

---

## Repository Layout

```
app/
  connectors/        reddit.py · youtube.py · themealdb.py · rss.py
  db/                base.py · session.py · models.py
  routes/            recipes.py · ingredients.py · ui.py · schemas.py
  static/            meal_plan.js · recipes.js
  templates/         base.html · meal_plan.html · recipes.html
  config.py          Settings (thresholds, API keys, discovery params)
  main.py            FastAPI app entrypoint
  pipeline.py        Weekly pipeline orchestrator (5 steps)
  discovery.py       Source discovery (Reddit + YouTube)
  extractor.py       Claude-based ingredient extraction
  normaliser.py      Ingredient name normalisation + synonym map
  scoring.py         Engagement formulas, source scoring, promotion
  schemas.py         Ingest-layer Pydantic schemas

alembic/versions/    9 migrations (full schema history)

scripts/
  run_pipeline.py          CLI entry point for weekly pipeline
  run_extraction.py        Standalone extraction runner
  smoke_test.py            Phase 1+2 production smoke test (7 checks)
  api_smoke_test.py        Phase 3+ API live smoke test (15 checks)
  backfill_canonical_names.py  One-time utility (completed 2026-03-29)

tests/               13 test modules · 258 tests total

.github/workflows/
  test.yml              Unit tests on push/PR
  integration.yml       Integration tests (manual)
  smoke_test.yml        Phase 1+2 smoke test (manual)
  api_smoke_test.yml    Phase 3+ API smoke test (manual)
  extract_ingredients.yml  Standalone extraction run (manual)
  weekly_pipeline.yml   Full pipeline (Sunday 08:00 UTC + manual)

railway.toml          Railway deployment config (nixpacks + start command)
.python-version       Pins Python 3.11 for Railway/nixpacks
requirements.txt      All runtime + test dependencies
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Ingredient matching | `ingredient_name` + `canonical_name` ilike OR | Handles spelling variants and prep-word noise |
| Source scoring | Recency-weighted avg + completeness bonus | Rewards sources with well-structured recipes |
| Promotion gate | Score ≥ 0.75 AND content_count ≥ 2 | Prevents one-run viral videos from polluting active sources |
| Extraction dedup | Skip if `Ingredient` rows already exist for `recipe_id` | Idempotent pipeline runs |
| Extraction resilience | Per-recipe try/except + rollback on commit failure | One DB timeout doesn't abort the whole batch or poison subsequent steps |
| API tests | SQLite StaticPool in-memory | No Postgres needed in CI; all connections share one DB |
| Frontend serving | FastAPI StaticFiles + Jinja2 | No separate server; same repo and deployment |
| Collapse toggle | Vanilla JS `.classList.toggle('show')` | Bootstrap JS global unreliable on Railway CDN at runtime |
| YouTube stats batching | Chunk IDs in groups of 50 | YouTube `videos.list` hard limit of 50 IDs per request |
| RSS title extraction | Parse first line of `raw_content`, strip `"Title: "` prefix | Consistent across all source types without extra DB columns |

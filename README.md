# MealEngineV2

A pipeline that ingests recipes from Reddit and YouTube, extracts structured ingredients, and generates meal plans.

## Project phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Ingest raw recipes from Reddit and YouTube into the database | Done |
| 1.5 | Source registry, quality scoring, discovery sweep, weekly scheduler | Done |
| 2 | Extract ingredients from raw content using Claude | Next |
| 3 | Generate meal plans, cook books, and grocery lists | Planned |

---

## Local setup

### Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) project (free tier is fine) — provides the PostgreSQL database
- A [YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com) key (only needed to ingest YouTube recipes)

### 1. Clone and install

```bash
git clone https://github.com/jacksoncslaiCanada/MealEngineV2.git
cd MealEngineV2
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres
YOUTUBE_API_KEY=AIza...
```

- **`DATABASE_URL`**: Copy the connection string from your Supabase project under
  *Project Settings → Database → Connection string → URI*.
  Replace `[YOUR-PASSWORD]` with the database password you set when creating the project.
- **`YOUTUBE_API_KEY`**: Only needed for YouTube ingestion. Leave it empty or omit it to skip YouTube.

### 3. Run database migrations

```bash
alembic upgrade head
```

This creates two tables: `raw_recipes` (recipe content) and `sources` (tracked channels and subreddits).

### 4. Run unit tests

```bash
pytest tests/ -v
```

All 76 unit tests should pass. No external services are called — everything is mocked.

---

## Running the weekly pipeline

The pipeline ingests new content from all active sources, recomputes quality scores, runs the discovery sweep, and promotes high-scoring candidates. It is triggered automatically every Sunday at 08:00 UTC by the GitHub Actions scheduler, but you can also run it manually.

### Locally

```bash
python scripts/run_pipeline.py
```

Exits with code `0` if all four steps complete cleanly, or `1` if any step raised an error (errors are shown in the summary, the remaining steps always run).

### Via GitHub Actions (manual trigger)

1. Go to your repository on GitHub
2. Click the **Actions** tab
3. Select **Weekly Pipeline** from the left sidebar
4. Click **Run workflow → Run workflow**

Required secrets (see [GitHub secrets setup](#github-secrets) below):
- `DATABASE_URL`
- `YOUTUBE_API_KEY`

---

## Running integration tests

Integration tests call the real Reddit and YouTube APIs. They are excluded from the default test run and must be invoked explicitly.

### On your local machine

```bash
# Reddit only (no credentials needed)
pytest -m integration -k reddit -v -s

# YouTube only (requires YOUTUBE_API_KEY in .env)
pytest -m integration -k youtube -v -s

# Both
pytest -m integration -v -s
```

The `-s` flag prints a preview of the first 300 characters fetched from each source so you can visually confirm the data looks usable.

### On GitHub Actions

1. Go to your repository on GitHub
2. Click the **Actions** tab
3. Select **Integration Tests** from the left sidebar
4. Click **Run workflow → Run workflow**

The workflow runs Reddit and YouTube tests as separate steps.

> **Note:** Reddit tests may show as failed in CI — Reddit frequently blocks GitHub runner IP addresses with a `403 Blocked` response. This does not prevent the YouTube step from running. If Reddit works locally but fails in CI, this is expected behaviour.

---

## GitHub secrets

Both the weekly pipeline and the test workflow require secrets configured at *Settings → Secrets and variables → Actions*:

| Secret | Required by | Description |
|--------|-------------|-------------|
| `DATABASE_URL` | Tests, Weekly Pipeline | PostgreSQL connection string |
| `YOUTUBE_API_KEY` | Tests, Weekly Pipeline, Integration Tests | YouTube Data API v3 key |

If `YOUTUBE_API_KEY` is not set, YouTube steps are skipped (not failed).

---

## Configuration

Scoring and discovery behaviour is controlled by these values in `app/config.py` (overridable via `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCE_QUALITY_THRESHOLD` | `0.6` | Candidates above this score are auto-promoted to active |
| `SOURCE_SCORE_WINDOW` | `20` | Number of recent recipes used to compute a source's quality score |
| `SOURCE_SCORE_DECAY` | `0.9` | Exponential recency weight — `0.9^i` for the `i`-th most recent recipe |
| `DISCOVERY_MIN_VIDEO_COUNT` | `5` | Minimum videos a YouTube channel must have to become a candidate |
| `DISCOVERY_MIN_SUBREDDIT_HITS` | `3` | Minimum search-result appearances for a subreddit to become a candidate |

---

## Project structure

```
app/
  config.py            # Settings (loaded from .env, overridable via env vars)
  schemas.py           # Pydantic schemas shared across connectors
  scoring.py           # Engagement formulas, source quality scoring, auto-promotion
  discovery.py         # Discovery sweep — finds candidate sources from existing API results
  pipeline.py          # Weekly pipeline orchestrator (ingest → score → discover → promote)
  connectors/
    reddit.py          # Fetches posts from Reddit public JSON API
    youtube.py         # Searches YouTube and fetches transcripts
  db/
    models.py          # SQLAlchemy ORM models (raw_recipes, sources tables)
    base.py            # Declarative base
    session.py         # DB session factory

scripts/
  run_pipeline.py      # CLI entry point for the weekly pipeline

alembic/               # Database migration scripts
  versions/
    3e1385ebf5eb_...   # Create raw_recipes table
    a9f2b1c3d4e5_...   # Add sources table + engagement columns to raw_recipes

docs/
  source-registry-design.md  # Full design doc for Phase 1.5

tests/
  test_reddit.py       # Unit tests for Reddit connector (mocked)
  test_youtube.py      # Unit tests for YouTube connector (mocked)
  test_scoring.py      # Unit tests for engagement + quality scoring
  test_discovery.py    # Unit tests for Reddit + YouTube discovery sweep
  test_pipeline.py     # Unit tests for weekly pipeline orchestration
  test_integration.py  # Integration tests (real APIs, opt-in)

.github/workflows/
  test.yml             # Run unit tests on every push
  integration.yml      # Run integration tests (manual trigger)
  weekly_pipeline.yml  # Run weekly pipeline every Sunday 08:00 UTC
```

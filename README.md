# MealEngineV2

A pipeline that ingests recipes from Reddit and YouTube, extracts structured ingredients, and generates meal plans.

## Project phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Ingest raw recipes from Reddit and YouTube into the database | Done |
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

### 4. Run unit tests

```bash
pytest tests/ -v
```

All 14 unit tests should pass. No external services are called — everything is mocked.

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

#### Required GitHub secret

Before running the workflow, add your YouTube API key as a repository secret:

1. Go to *Settings → Secrets and variables → Actions*
2. Click **New repository secret**
3. Name: `YOUTUBE_API_KEY`, Value: your API key

If the secret is not set the YouTube tests will be skipped (not failed) with a clear message.

---

## Project structure

```
app/
  config.py          # Settings loaded from .env
  schemas.py         # Pydantic schema shared across connectors
  connectors/
    reddit.py        # Fetches posts from Reddit public JSON API
    youtube.py       # Searches YouTube and fetches transcripts
  db/
    models.py        # SQLAlchemy ORM model (raw_recipes table)
    base.py          # Declarative base
    session.py       # DB session factory

alembic/             # Database migration scripts
tests/
  test_reddit.py     # Unit tests for Reddit connector (mocked)
  test_youtube.py    # Unit tests for YouTube connector (mocked)
  test_integration.py# Integration tests (real APIs, opt-in)
```

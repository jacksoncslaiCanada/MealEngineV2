# Source Registry & Scoring Design

## Problem

Sources (YouTube channels, subreddits) are hardcoded in `reddit.py` and `youtube.py`. There is no mechanism to:
- Track which sources exist and whether they are active
- Measure how good a source is over time
- Discover new sources automatically
- Promote or reject candidate sources based on quality

This document defines the architecture for a managed source registry with automatic discovery and content-level scoring.

---

## Overview

Two concerns are separated:

1. **Source Registry** — a managed list of channels/subreddits, each with a lifecycle status and a computed quality score
2. **Content Signals** — engagement metadata captured at fetch time per recipe, used to compute source scores

Discovery is a periodic sweep that finds candidate sources from the same APIs already in use, without requiring new credentials.

---

## Database Schema

### `sources` table

Channels and subreddits are first-class entities.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `platform` | VARCHAR(16) | `"reddit"` or `"youtube"` |
| `handle` | VARCHAR(256) | Subreddit name or YouTube channel ID |
| `display_name` | VARCHAR(256) | Human-readable name |
| `status` | VARCHAR(16) | See lifecycle below |
| `quality_score` | FLOAT | 0.0–1.0, recomputed weekly |
| `content_count` | INTEGER | Total recipes ingested from this source |
| `added_at` | TIMESTAMPTZ | When the source was first seen |
| `last_ingested_at` | TIMESTAMPTZ | Last time content was pulled |

**Unique constraint:** `(platform, handle)`

### `raw_recipes` additions

Engagement signals captured at fetch time, per recipe.

| Column | Type | Notes |
|---|---|---|
| `source_fk` | INTEGER FK → `sources.id` | Links recipe to its source |
| `engagement_score` | FLOAT | Platform-normalised 0–100 score |
| `content_length` | INTEGER | Character count of `raw_content` |
| `has_transcript` | BOOLEAN | YouTube only; NULL for Reddit |

**Engagement score computation:**
- Reddit: `log10(upvotes + 1) * upvote_ratio * 10`, capped at 100
- YouTube: `log10(views + 1) * (likes / (likes + dislikes + 1)) * 10`, capped at 100

Both formulas use a log scale so a post with 10,000 upvotes isn't 1,000× better than one with 10 — the curve flattens out, which prevents a small number of viral outliers from dominating quality scores.

---

## Source Lifecycle

```
candidate ──── quality_score > 0.6 OR manual approve ────→ active
    │                                                           │
    └──── manual reject ──────────────────────────────→ rejected
                                                            │
                                                   active ──┴──→ paused
```

| Status | Meaning |
|---|---|
| `candidate` | Discovered automatically; not yet ingested |
| `active` | Ingested on each weekly run |
| `paused` | Temporarily suspended from ingestion |
| `rejected` | Permanently excluded; never ingested |

Only `active` sources are pulled during the weekly ingest run.

---

## Source Quality Score

Recomputed after each weekly ingest:

```
quality_score = weighted average of engagement_score
                for the last 20 recipes from this source,
                weighted by recency (newer = higher weight)
```

Exponential decay weighting: `weight[i] = 0.9^i` where `i=0` is the most recent post.

A source with consistently high-engagement recent content scores near 1.0. A source that was good 6 months ago but has declined will score lower.

---

## Discovery Sweep

The discovery sweep runs as a separate, cheaper step after the weekly ingest. It does not ingest content — it only finds new candidates.

### Why it is nearly free

The sweep reuses the same API calls already made during ingestion. For YouTube, search queries are already being run to fetch videos — the sweep just reads the channel metadata from those same results. For Reddit, the hot-post feeds are already being fetched — the sweep reads the subreddit name from each result. No extra API quota is consumed beyond a small number of additional lookup calls.

### Reddit discovery — two directions

**Direction 1: Sideways from known sources (author cross-posting)**

You are already ingesting from `r/EatCheapAndHealthy`. A top post there was written by `u/MealPrepKing`. The sweep checks that user's recent post history (public, no auth needed). If they also post frequently to `r/Bento` or `r/veganrecipes` — subreddits not already in your `sources` table — those subreddits become candidates. The logic: if a prolific contributor to one known-good subreddit is also active elsewhere, that community is worth investigating.

**Direction 2: Keyword search across Reddit**

Reddit's search endpoint is queried for `"recipe"` and `"cooking"`. Results come from many different subreddits. Any subreddit that appears 3+ times in those results and is not already in `sources` is inserted as a candidate. This catches entirely new communities that have no connection to your existing sources.

```
For each ACTIVE Reddit source:
    1. Fetch its current top posts
    2. For each post, note the author
    3. Fetch that author's recent post history
    4. For each subreddit they post to:
        - If subreddit not in sources table AND cooking-adjacent → candidate

Also:
    5. Search Reddit for "recipe" and "cooking"
    6. Tally which subreddits appear in results
    7. Any subreddit with ≥ 3 results and NOT in sources → candidate
```

### YouTube discovery — channel extraction

The sweep reuses the same search queries (`"recipe"`, `"easy dinner recipe"`, etc.) already used for ingestion. Instead of saving the videos, it looks at which **channel** each video belongs to.

For any channel not already in `sources`:
1. Check how many of its videos are recipe-tagged — fewer than 5 means too little signal, skip it
2. Pull its last 5 videos and compute their average `engagement_score`
3. If average > 0.6 → auto-promote directly to `active`; it will be ingested next Sunday
4. If average ≤ 0.6 → insert as `candidate`; sits in the queue until it earns more signal

```
For each active search query:
    1. Run the query (same as current fetch)
    2. Extract channel_id from each result video
    3. For any channel NOT already in sources:
        a. Fetch channel's video count for recipe-tagged content
        b. If count < 5 → skip (insufficient signal)
        c. Fetch last 5 videos, compute average engagement_score
        d. If avg engagement_score > 0.6 → insert with status = "active"
           else → insert with status = "candidate"
```

### What lands in the database after a sweep

- 0–N new rows in `sources` with `status = "candidate"` or `status = "active"`
- No content rows are written — the sweep is read-only with respect to `raw_recipes`
- A summary is printed to stdout: `"Discovery: 3 new candidates, 1 auto-promoted to active"`

### The human review moment (optional)

After the sweep, review candidates with a simple query:

```sql
SELECT display_name, platform, quality_score, added_at
FROM sources
WHERE status = 'candidate'
ORDER BY quality_score DESC;
```

Options:
- Leave them alone — auto-promotion handles high scorers over time
- Set `status = 'rejected'` for anything clearly off-topic
- Set `status = 'active'` to manually fast-track a promising source

You only need to intervene for edge cases. The system handles the rest.

---

## Weekly Run Sequence

```
Sunday 08:00 UTC
│
├── 1. Ingest content from all ACTIVE sources
│       ├── Pull new posts/videos
│       ├── Store raw_content + engagement signals
│       └── Update last_ingested_at, content_count on source row
│
├── 2. Recompute quality_score for all active sources
│       └── Weighted average of last 20 content pieces per source
│
├── 3. Discovery sweep
│       ├── Reddit: inspect author profiles + subreddit search
│       ├── YouTube: extract channel IDs from search results
│       └── Insert new candidates into sources table
│
└── 4. Auto-promote candidates above threshold
        └── quality_score > 0.6 → status = "active"
```

---

## What You Curate vs. What Is Automatic

| Task | Owner |
|---|---|
| Initial seed list of known good sources | You, once |
| Discovering candidate channels/subreddits | Automatic (discovery sweep) |
| Scoring content from active sources | Automatic, weekly |
| Recomputing source quality scores | Automatic, weekly |
| Promoting high-scoring candidates | Automatic (threshold) |
| Rejecting bad candidates | You (optional, short review list) |
| Adjusting scoring thresholds | You (config value) |

---

## Configuration

These values will live in `app/config.py`:

```python
SOURCE_QUALITY_THRESHOLD = 0.6      # Auto-promote candidates above this score
SOURCE_SCORE_WINDOW = 20            # Number of recent recipes used to compute score
SOURCE_SCORE_DECAY = 0.9            # Exponential decay weight per step back in time
DISCOVERY_MIN_VIDEO_COUNT = 5       # Min recipe videos before a YouTube channel is a candidate
```

---

## Implementation Phases

### Phase 1.5a — Source Registry ✓
- `sources` table + migration (`alembic/versions/a9f2b1c3d4e5_add_sources_table.py`)
- `source_fk`, `engagement_score`, `content_length`, `has_transcript` added to `raw_recipes`
- Both connectors updated: write engagement signals, link recipes to source FK via `get_or_create_source()`
- `app/scoring.py`: `compute_reddit_engagement()`, `compute_youtube_engagement()`, `recompute_source_scores()`, `auto_promote_candidates()`, `get_or_create_source()`, `mark_source_ingested()`
- `SourceSchema` added to `app/schemas.py`; `RawRecipeSchema` extended with `source_handle`, `source_display_name`, `engagement_score`, `has_transcript`
- Scoring config values added to `app/config.py`

### Phase 1.5b — Discovery Sweep ✓
- `app/discovery.py`: `discover_reddit_sources()` (author cross-posting + keyword search), `discover_youtube_sources()` (channel extraction with video count and engagement gating), `run_discovery_sweep()` orchestrator
- `DiscoverySummary` dataclass: `new_candidates`, `auto_promoted`, `skipped`, `new_sources`
- `_is_cooking_adjacent()` keyword filter for Reddit subreddit names

### Phase 1.5c — Pipeline & Scheduler ✓
- `app/pipeline.py`: `run_weekly_pipeline()` orchestrates ingest → score → discover → promote; per-platform error isolation; `PipelineReport` dataclass
- `scripts/run_pipeline.py`: CLI entry point, exits 0/1 based on errors
- `.github/workflows/weekly_pipeline.yml`: cron `0 8 * * 0` (Sunday 08:00 UTC) + `workflow_dispatch`

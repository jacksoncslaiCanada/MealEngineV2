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

### Reddit discovery

```
For each ACTIVE Reddit source:
    1. Fetch its current top posts
    2. For each post, check the author's profile (public)
    3. If author posts frequently to other cooking-related subreddits
       that are NOT in the sources table → add as candidate

Also:
    4. Search Reddit for "recipe" and "cooking" and inspect
       which subreddits the results come from
    5. Any subreddit with ≥ 3 results and NOT already in sources → candidate
```

### YouTube discovery

```
For each active search query:
    1. Run the query (same as current fetch)
    2. Extract the channel_id from each result
    3. For any channel NOT already in sources:
        a. Count how many recipe-tagged videos it has
        b. If count ≥ 5 → insert as candidate with status = "candidate"
        c. Fetch last 5 videos, compute average engagement_score
        d. If avg engagement_score > 0.6 → auto-promote to "active"
           otherwise leave as "candidate" for manual review
```

### What happens to candidates

After each discovery sweep:
- Candidates with `quality_score > 0.6` (enough data to judge) are auto-promoted to `active`
- Candidates with `quality_score ≤ 0.6` sit in the candidate queue
- A short weekly report lists new candidates for optional human review

You only need to intervene if you want to:
- Reject a candidate that auto-promotion would otherwise promote
- Manually promote a candidate before it earns enough score

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

### Phase 1.5a — Source Registry (next)
- Create `sources` table + migration
- Add `source_fk`, `engagement_score`, `content_length`, `has_transcript` to `raw_recipes`
- Update connectors to write engagement signals and link to source FK
- Move hardcoded source lists into the `sources` table (seeded via migration)

### Phase 1.5b — Scoring
- Implement `recompute_source_scores()` function
- Implement engagement score formulas for Reddit and YouTube

### Phase 1.5c — Discovery Sweep
- Implement `run_discovery_sweep()` for Reddit and YouTube
- Implement auto-promotion logic
- Add candidate summary report (stdout or log)

### Phase 1.5d — Scheduler
- GitHub Actions scheduled workflow (Sunday 08:00 UTC)
- Runs: ingest → score → discover → promote

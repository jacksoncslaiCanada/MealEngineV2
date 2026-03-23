# MealEngineV2 — Implementation & Testing Plan

## Stack
- **Backend:** Python + FastAPI
- **Database:** PostgreSQL
- **Ingredient Extraction:** Claude API

---

## Phase 1 — Recipe Source Connectors

**Goal:** Reliably pull raw recipe data from Reddit and YouTube.

### Implementation
- Reddit connector via Reddit API — fetch posts/comments containing recipes
- YouTube connector via YouTube Data API — fetch video title, description, transcript
- Normalize raw data into a common schema:
  ```
  { source, source_id, raw_content, url, fetched_at }
  ```
- Persist raw records to PostgreSQL

### Tests
- Unit tests: mock API responses, verify normalization schema
- Integration tests: live fetch of 1 known recipe from each source
- DB test: raw record written and retrievable

**Gate:** Raw data from both sources lands in the DB reliably.

---

## Phase 2 — Ingredient Extraction

**Goal:** Parse raw recipe content into structured ingredients, maintaining source linkage.

### Implementation
- Feed raw recipe text to Claude API with a structured extraction prompt
- Output schema:
  ```
  { ingredient_name, quantity, unit, recipe_id, source_id }
  ```
- Store extracted ingredients in PostgreSQL with FK back to the raw recipe record

### Tests
- Unit tests: mock Claude API response, verify parsed output
- Accuracy test: compare extracted ingredients vs. manually labelled ground truth (target ≥ 90% accuracy)
- DB test: ingredients stored and queryable by recipe

**Gate:** Ingredient extraction hits accuracy threshold on a sample dataset.

---

## Phase 3 — Tier 1 Recipe Generation (Pre-set)

**Goal:** Generate usable pre-set recipes and grocery lists from stored ingredients.

### Implementation
- Recipe assembly engine: select ingredients from DB, build structured recipe object
- Grocery list generator: aggregate ingredients across selected recipes
- Output: structured recipe card + grocery list

### Tests
- Unit tests: recipe builder with mock ingredient data
- Output validation: generated recipe contains all required fields
- End-to-end test: source → extract → generate a complete recipe + grocery list

**Gate:** A user can get a valid recipe and grocery list from ingested data.

---

## Phase 4 — Tier 2/3 Customization & Subscription

**Goal:** Allow cookbook adjustments (Tier 2) and full mix-and-match customization (Tier 3), gated by subscription.

### Implementation
- **Tier 2:** User can swap ingredients, adjust servings, save cookbook
- **Tier 3:** Fully customizable meal plans (subscription-gated)
- Auth system + subscription enforcement layer

### Tests
- Unit tests per customization feature
- Subscription gate tests: verify Tier 3 features are inaccessible without subscription
- User flow integration tests: complete Tier 2 and Tier 3 workflows

**Gate:** Tiers are cleanly separated and subscription enforcement works end-to-end.

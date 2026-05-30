# Rebuild Log

A running journal of the Cookmarks v2 rebuild — what was done, the context, and
the decisions behind it. Append new entries at the bottom. `CLAUDE.md` documents
the **current state**; this file records **how and why** we got there.

## Background

Cookmarks v1 is a Django/HTMX app that extracts and organises recipes from a
personal Calibre ebook library (AI extraction via LangGraph, sqlite-vec semantic
search, BYOK Gemini/OpenRouter). v2 rebuilds it on a typed-Python **FastAPI**
backend + **SvelteKit** SPA, centred on an **agent-verifiable harness**. v1 is a
reference/guide; v2 reconsiders core concepts from first principles — except
recipe extraction, which is proven and carried over largely as-is.

Starting point for this log: the v2 scaffold (FastAPI + Svelte SPA + verify
harness) already existed on the `v2` branch.

## 2026-05-30 — Data models

**Goal:** define the v2 persistence layer (SQLAlchemy 2.0), using v1's Django
models as evidence of need rather than a template.

**Framing decisions (first principles):**

- The name "cookmarks" does *not* imply an open/locate-in-book feature. The app
  is simply "extract and organise recipes from digital cookbooks." (Dropped an
  earlier over-reach toward provenance/anchor modelling.)
- **Single-user / self-hosted** for now — no `User`/auth; `Config` stays a singleton.
- **Personal layer = favourites + lists only** (no notes/ratings/cooked-log).
- **Source of truth:** Calibre owns book files + bibliographic metadata; our DB
  owns the value we add (recipes, organisation, search index). `Book.path` /
  `calibre_id` are refreshable pointers — nothing durable hangs off them.

**Schema decisions:**

- Shared `UUIDAuditBase` (UUID PK + tz-aware `created_at`/`updated_at`). UUIDs
  store as `CHAR(32)` hex on SQLite; `str(uuid)` is hyphenated — matters for
  vec-table key consistency.
- `StrEnum`s for choice fields (`AIProvider`, `ExtractionStatus`,
  `ExtractionMethod`), stored by value. `ExtractionStatus` gains `QUEUED`/`FAILED`
  over v1's three.
- **Recipe identity stable across re-extraction:** reconcile by normalised name
  within a book (update in place, not wipe-and-recreate) so favourites/lists
  survive. A *contract on the extraction task*; needs no schema beyond stable UUID PKs.
- Ingredients/instructions stay **flat string lists** (mirror v1); no structured parsing.
- **Thin models:** v1's `Book` filesystem helpers are *not* ported onto the ORM
  (they belong in a Calibre service).
- `Config` kept **minimal** (provider + write-only `api_key`); grows as later
  milestones need it.
- `RecipeListItem.position` added for future user-ordering of lists.
- `PRAGMA foreign_keys=ON` added to the connection listener so `ON DELETE` rules
  actually fire on SQLite.
- Embedding-staleness fields deferred to the search milestone.

**ExtractionReport → ExtractionRun:** initially trimmed to lifecycle/cost/outcome,
then — once we confirmed extraction is the proven area carried over as-is —
restored to mirror v1 faithfully: `extraction_method`,
`images_in_separate_chapters`, `images_can_be_matched`, `total_chapters`,
`chapters_processed`. Still dropped: `thread_id` (LangGraph checkpoint id) and
`queued_at` (folded into `created_at`).

**Outcome:** `app/models/` (one module per aggregate) + `enums.py` +
`UUIDAuditBase`; initial Alembic migration; `make migrate` target. `ruff`/`ty`
clean. Commit `fac1682`.

## 2026-05-30 — Dev data: v1 → v2 import

**Goal:** seed the v2 DB with real production data so the UI can be built against
real content.

**Source:** v1 production SQLite at `~/docker/cookmarks/data/db.sqlite3` (~354 MB).
Read-only throughout; worked from a checkpointed copy.

**Key finding:** v1's `recipe_embeddings` (vec0) keys on the **hyphenated** UUID
(`str(recipe.id)`), while `core_recipe.id` stores **hex** (no hyphens) — same
UUID, different representation. v2 stores hex and will look up embeddings via
`str(recipe.id)` (hyphenated), so copying embeddings **as-is** is forward-compatible.

**Mapping decisions:** `extraction_report_id` → `extraction_run_id`; drop
`queued_at` / `thread_id`; `NULL` ingredients/instructions → `[]`; assign
`RecipeListItem.position` from v1's created-at order; validate `Config.ai_provider`
against the enum (else `NULL`). Django infra tables (`auth_*`, `django_*`,
`checkpoints`, `django_q_*`) skipped.

**Tooling:** `backend/scripts/import_v1_data.py` — read-only on the source, clears
+ repopulates the v2 app tables, copies all relational tables + the vec
embeddings, preserves UUIDs. Re-runnable; `--source`, `--no-embeddings`.

**Outcome:** imported 192 books, 13,403 recipes, 4,968 keywords, 78,334 keyword
links, 135 extraction runs, 3 lists / 9 items, 1 config, 13,275 embeddings.
Verified: no FK violations, ORM read-back, enum round-trip, working vec search.
Dev DB ~218 MB (gitignored). Commit `8b7c519`.

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

## 2026-05-31 — UI design direction + `DESIGN.md`

**Goal:** choose a visual/interaction language for the v2 UI and capture it so a
fresh agent can build the real app without re-deriving it.

**Process:** explored **four** distinct directions as self-contained static HTML
mockups over the *real* imported data (actual covers, recipe photos extracted from
the EPUBs, real titles/counts), served on `0.0.0.0` for remote review:
*Editorial* (warm print-magazine, Fraunces), *Market* (bold grocer signage,
Archivo + marquee), *Catalogue* (library card-index, Newsreader + Plex Mono), and
*Kitchen* (cosy warm-dark, Bricolage Grotesque). Built in parallel by subagents.

**QA:** drove every screen via Playwright at 1280 and 390. One real bug found and
fixed — Kitchen gated reveals behind an `IntersectionObserver` (`threshold: 0.05`)
that never fired on tall containers, leaving whole sections stuck at `opacity:0`;
the lesson (no scroll-gated reveals that can strand content) is recorded in
`DESIGN.md`. Market/Kitchen mobile "overflow" was a fixed-layer screenshot artefact
(no real horizontal scroll).

**Decision:** **Catalogue**, refined by mixing in the **Anthropic brand language**
(Geist) → a *"Catalogue × Anthropic"* direction: warm
ivory `#faf9f5` + ink `#141413` + clay `#d97757` accent; Schibsted Grotesk
(headings) + Source Serif 4 (body) + IBM Plex Mono (metadata); numbered, text-first
catalogue layouts. Added a real **no-image recipe** page ("Dal", Felicity Cloake) —
absence is treated as a designed typographic state, since most recipes lack images.
An initial "/" slash motif was **rejected and removed from the language**.

**Outcome:** `DESIGN.md` — a standalone, conversation-free UI design-language spec
(tokens, components, screens; referenced from `CLAUDE.md`). The exploration mockups
were removed once the spec captured the decisions, so `DESIGN.md` alone is enough to
build the UI. Suggested first production slice: `/books`.

## 2026-05-31 — `/books` vertical slice (first real feature)

**Goal:** the first end-to-end feature on the v2 stack — a books library page —
landing the patterns every later milestone reuses: a Pydantic response-schema layer,
a typed+validated frontend API client, the `DESIGN.md` §3 tokens + self-hosted fonts,
and the **first real verifiable unit** (retiring the Smoke self-test).

**Scope (decided with the user):** basic grid only — no search/sort/filter yet
(the §5 controls come later). Book **covers are in**, served from a **config-driven**
library location.

**Backend:**

- `GET /api/books` → `BookSummary` (id, title, author, recipe_count, has_cover,
  pubdate). Recipe counts come from one grouped `outerjoin + count(Recipe.id)` query
  (not `*`, so the 89 zero-recipe books correctly read 0), default order
  `created_at DESC`. New `app/schemas/` layer; router wired in `api/router.py`.
- `GET /api/books/{id}/cover` streams `cover.jpg` via `FileResponse`, with a
  `is_relative_to` path-traversal guard. `has_cover` is a per-book file-existence check.
- **Paths are no longer absolute in the DB.** `Book.path` now stores a path *relative*
  to `settings.calibre_library_path` (new setting, default `~/books/calibre-all`); the
  v1 import strips the baked-in `/books/` prefix (`copy_books`). The library can now be
  relocated by config alone. Re-seeded: 192 books, all 192 covers resolve.

**Frontend:**

- `DESIGN.md` §3 tokens + `.label`/`.mono` helpers + `fadeUp`/reduced-motion landed in
  `app.css` (verdict colours preserved); fonts self-hosted via `@fontsource`
  (Schibsted Grotesk / Source Serif 4 variable / IBM Plex Mono).
- Presentational components: `BookCard` (cover plate **or** §7 no-cover title-plate,
  clay accession number, serif title, recipe count / "— pending extraction") and
  `BooksLibrary` (responsive grid 4→3→2→1, total count, the `data-verify-*` contract).
- `$lib/api/books.ts` validates the response with Zod (the response-validation pattern);
  `/books` route fetches, maps, and renders with loading/error states; nav gains a
  clay-underline **Books** link.

**Verification:** the Smoke unit was deleted and `harness.test.ts` repointed at the new
unit's `populated` (PASS) / `contract-lie` (deliberate FAIL) fixtures. New backend
`conftest.py` (temp-sqlite fixture + `get_session` override) + `test_books.py`.
`make verify`/`check`/`test` all green; Playwright at 1280 and 390 confirmed real
covers, the §7 plates, the pending state, accession numbers, single-column mobile
reflow with no horizontal scroll, and the verify dashboard (smoke gone, `books-library`
passing, `contract-lie` the sole intended FAIL).

**Home page + app shell (same slice).** The books page can't be judged in isolation, so
the slice also landed the surrounding frame. `GET /api/home` returns a stats ledger
(books · recipes · keywords) and a **book of the day** — a daily, stable rotation among
books that actually have recipes, carrying its description. The landing (`HomeLanding`,
verifiable unit `home-landing`) is a **single book-of-the-day feature** — cover plate
(or §7 fallback), large italic-serif title, author, a plain-text description excerpt,
recipe count, and a browse link; the `/` route replaces the scaffold placeholder.
(`GET /api/home` also returns a library stats ledger — books · recipes · keywords — kept
for later use, though the landing itself shows only the feature.) A warm footer was added
to the shell; the wordmark (nav + footer) is set in **italic Source Serif 4**, an
editorial masthead matching the display titles; nav stays **live links only**
(Home · Books) until the Recipes/Lists slices land. Per the agreed scope, the home
**featured-recipes index** was deferred (no recipe-row component yet). Shared backend tidy-up: `app/covers.py`
(`cover_path`/`has_cover`) and `SessionDep` moved to `app/db.py`. Two data-shape fixes
found via Playwright: Calibre descriptions carry HTML (stripped to a plain-text excerpt,
separator underscore-runs collapsed) and a long unbreakable token overflowed the mobile
grid (fixed with `min-width:0` + `overflow-wrap`, and `--page-h` made responsive).
`home-landing` (populated + no-feature probe) joins the green matrix.

## 2026-05-31 — Books search + sort

The deferred §5 controls, scoped down with the user: a client-side **search** box
(substring over title + author) and a **sort dropdown** (Recently added / Title A–Z /
Author / Most recipes) — **no** author filter (search covers author) and **no** URL state
(filters are in-component). All over the already-loaded `books` prop, so `BooksLibrary`
stays presentational.

- Accession numbers are now derived from each book's position in the full (recently-added)
  library and looked up by id, so sorting/filtering never renumbers a book.
- The contract gained `data-verify-{total,sort,query,first}`; the unit's fixtures now drive
  the controls via `act` (`type` into the search box and the `<select>`) — `search-match`,
  `sort-title`, and a `no-results` probe — with invariants asserting the filtered count,
  matching titles, sort order, and the calm no-results message. The `<select>` is wired on
  `oninput` so the harness can drive it (its `act` has no native select support).
- Calm states: a "No books match …" message distinct from the empty-library "No books yet";
  a clay focus ring (`:focus-visible`) was added globally for the new controls.

Verified headless (matrix, with `flushSync`) and live via Playwright — confirming the
synchronous read pitfall: Svelte 5 batches DOM updates, so live assertions must await a
tick where the harness gets it for free.

## 2026-05-31 — Drop accession numbers; recipe-count circle

Per the user: the `CM-001` **accession numbers were removed throughout** — from `BookCard`
(and the `BooksLibrary` accession map), the verify invariants, and `DESIGN.md` (§2, §4's
accession bullet, §5 book card + recipe masthead, §7 plate, §3.2 mono role). The numbered
**recipe-index** motif (`001, 002…` leading list rows) stays — only the per-book accession
id is gone.

Extraction state moved off a text tag and **onto the cover**: a clay **count circle** in the
top-right shows how many recipes were extracted; **unextracted books show no circle** (so
the old "— pending extraction" text is gone too). The circle folds its count into the card
link's accessible name and is otherwise `aria-hidden`. Verified live: 103 circles across the
192 covers, none on the 89 unextracted books.

## 2026-06-01 — Critical-review fixes (harness truthfulness + tooling)

A critical review of the v2 scaffold surfaced several spots where the green matrix was
papering over gaps in the verifiability thesis. Fixed all of them:

- **Isolation route showed a different instance than it verified.** `/verify/<unit>/<fixture>`
  rendered the component declaratively *and* ran `runFixture` on a second, hidden copy — so
  for any `act` fixture (search/sort) the screenshot showed the **unfiltered** view while the
  verdict reflected the filtered one. `runFixture` now takes `{ target, keepMounted }`; the route
  mounts into its on-screen node and verifies *that*. The screenshot can no longer disagree with
  the verdict. Confirmed live: `search-match` shows 2 cards + `query=modern` + `PASS`.
- **`probe` was overloaded and silently exempted real states from enforcement.** Split into two
  orthogonal flags: `probe` = adversarial *input* (still must `PASS`; ≥1 per unit), `expectFail` =
  the truthfulness sentinel (must `FAIL`). The matrix now asserts *every* non-`expectFail` fixture
  passes (probes included) and every sentinel fails. `no-results`/`long-title` are now enforced
  (`long-title` gained a real "renders in full" invariant); `contract-lie` became the lone
  `expectFail` sentinel.
- **The a11y verifier could never fail** (all `warn`). Promoted unnamed-button / unlabelled-input /
  alt-less-image to `fail` — load-bearing per DESIGN §8. No existing unit regressed.
- **The backend ↔ frontend contract was verified by nobody.** Added `contract/*.example.json` pinned
  from both sides: `backend/tests/test_contract.py` asserts each Pydantic model serialises to the
  example (and the live endpoints emit the same keys); `frontend/src/lib/api/contract.test.ts`
  asserts the Zod schemas accept it and reject a drifted copy. A one-sided rename now fails CI.
- **`make test` / CI ran the wrong pytest.** A stale console-script shebang (relocated worktree)
  let `uv run pytest` fall through to a system pytest with no `sqlite_vec`. Switched `make test`
  and `ci.yml` to `uv run python -m pytest`, matching the existing `python -m alembic` rationale.
- **Hygiene:** removed stray review screenshots from the repo root and gitignored Playwright MCP
  artefacts (`.playwright-mcp/`, `*-desktop.png`, `*-mobile.png`); fixed the stale port comment in
  the Makefile `dev` target (9789/9788).

All green: backend `pytest` 13 passed (4 new contract tests), `ruff`/`ty` clean; frontend `vitest`
14 passed (matrix 9, harness 2, contract 3), `svelte-check` 0/0, `build` OK. Verified live via
Playwright: dashboard 9 `PASS` / 1 `FAIL` (the `contract-lie` sentinel).

## 2026-06-01 — Book detail page ("The Index" layout)

The first detail view, landing the `/books/{id}` route the library grid already linked to.
Design chosen from four reviewed mockups (`mockups/book-detail/`): **Layout A "The Index"** —
a two-column editorial view (serif masthead + reading column; a sticky cover / actions /
metadata sidebar, its top aligned to the title).

- **Backend:** `GET /api/books/{id}` → `BookDetail` (schemas/book.py) with real model fields
  only — title, author, isbn, pubdate, description, total `recipe_count`, `has_cover`,
  `added` (calibre_added_at) — plus a **random sample of 10** recipes (`ORDER BY RANDOM()
  LIMIT 10`, `selectinload(keywords)`) as `RecipeRow` (id, name, keywords). 404 on unknown id.
  Tests in `test_books.py` (shape, ≤10 cap, keyword shape, empty book, 404); the seed gained
  two keywords (so `test_home` keyword count moved 0→2).
- **Frontend:** presentational `BookDetail.svelte` (`data-verify-unit="book-detail"` with
  `id / recipe-count / shown / has-cover / empty`), the `/books/[id]` route
  (onMount→`fetchBookDetail`→3-state), `fetchBookDetail` + Zod schemas, and shared
  `lib/title.ts` (clean-title / subtitle split, v1 `clean_title`) + `lib/html.ts`
  (Calibre-HTML→text, shared with Home). `book-detail.verify.ts` uses the post-merge
  convention: `populated / no-cover / no-recipes / no-subtitle` plus `long-title` &
  `many-keywords` **probes** (adversarial, must PASS) and a `contract-lie` **expectFail**
  sentinel; invariants on id, count, rows≤10=shown, main title, empty state, count circle,
  no-subtitle.
- **UI:** masthead (clean title + post-colon subtitle) + read-more description; a `RECIPES`
  label, recipe rows of **name + one line of keyword chips** (extra chips clip; no numbers)
  and a `+ N more` footer; sticky sidebar with the cover (count circle, §7 no-cover plate),
  dark **Read book** / outlined **Action** buttons (no-op), and an all-mono `LABEL · value`
  metadata ledger. No fabricated data; no eyebrow labels.
- **App-wide while here:** footer pinned to the viewport bottom (min-height flex column);
  clean titles (drop the post-colon subtitle) on the home feature; eyebrow labels removed
  from `BooksLibrary` + the `/books` loading state.
- **Cover-path fix (dev data):** covers resolved 0/192 — the seeded dev DB pre-dated the
  import script's `removeprefix(V1_LIBRARY_ROOT)` and still held absolute `/books/...` paths
  while `calibre_library_path` (`~/books/calibre-all`) expects them relative. Normalised the
  stale DB in place (`UPDATE books SET path = substr(path, 8)`); 192/192 covers now resolve.

Merged the concurrent critical-review work (above) in: migrated the verify unit to the new
`probe`/`expectFail` split and re-greened (`make check` + `make test`). Verified via Playwright
(1280×800 + 390×844): real cover + count circle, random-10 reshuffling, empty state, §7
no-cover plate, single-line tags, footer pinned on short pages, mobile reflow without
horizontal scroll.

## 2026-06-02 — Recipe extraction ported (LangGraph pipeline + AI providers)

v1's proven extraction stack ported onto the v2 backend — faithful in behaviour, re-fitted
to SQLAlchemy / Celery / typed-Python. Scope is the core extract-and-save flow; embeddings
(search milestone), keyword dedup (maintenance), and the HTTP trigger/resume endpoints (API
milestone) are deliberately out.

- **Plumbing.** New runtime deps `langgraph` / `langgraph-checkpoint-sqlite` / `lxml` /
  `google-genai`; `httpx` promoted dev→runtime (the OpenRouter client). New
  `Config.extraction_rate_limit_per_minute` column (default 256; migration `bcc69efeffc5`,
  `server_default='256'` backfills existing singleton rows) and `Settings.extraction_threads`
  (16, v1's default). `epub_path(book)` helper beside `cover_path` in `app/covers.py`.
- **Pure modules** under `app/services/`: `epub.py`, `rate_limiter.py`, `prompts.py`,
  `recipe_schema.json`, `extraction/{state,utils}.py` — near drop-ins. `RecipeData` (Pydantic
  v2: aliases + `capwords`/yields normalisation) at `app/schemas/extraction.py`.
- **AI provider package** `app/services/ai/` — greenfield for "more providers later": adding
  one is subclass + a `models` map + one `_complete`. `AIProvider` ABC with shared
  `extract_recipes` / `check_if_can_match_images`; a `ModelRole` enum decouples model choice
  from the stored file/block method; a typed frozen `Usage` (None-preserving `__add__`)
  replaces v1's usage dicts. `GeminiProvider`, `OpenRouterProvider` (retry/backoff on httpx),
  `StubProvider` (offline, keyless, content-varying recipe names so chapters don't collapse
  on dedupe). `get_config` / `get_ai_provider(session)` registry keyed on each provider's
  `name` — so the runtime ABC and the `AIProvider` *enum* never clash; a `requires_api_key`
  gate lets STUB through keyless while a network provider without a key resolves to `None`.
- **Graph** `app/services/extraction/graph.py` — the StateGraph ported verbatim in shape
  (analyse → file|block → validate → [await_human] → resolve_images → finalise, keeping the
  human-review `interrupt()` + SQLite checkpointer). v2 adaptations: each node opens its own
  `SessionLocal()` (JSON list columns reassigned so SQLAlchemy detects the change); usage
  accrues via `Usage.__add__`, cost rounded at the report boundary; `provider.model_for(...)`
  instead of class constants; a cached lazy `get_extraction_graph()` replaces v1's import-time
  `sqlite3.connect`, so importing the module touches no DB. Threading stays safe — the provider
  is built once on the main thread; worker threads only do network+parse.
- **Task layer** `app/tasks/extraction.py` — `extract_recipes_from_book(book_id, run_id?)` and
  `resume_extraction(run_id, response)` (the `update_state(as_node="await_human")` + re-invoke
  path), with thin `@celery_app.task` wrappers. `save_recipes_from_graph_state` reconciles by
  normalised name within the book (update-in-place → stable recipe identity, so favourites/list
  membership survive a re-run); a no-op `generate_recipe_embeddings` hook marks the search
  milestone's seam. The deterministic `thread_id = run_<id>` needs no stored column.
- **Tests** `tests/test_extraction.py` (23): routes; RecipeData/Usage/registry; DB-backed nodes
  (mocked epub/provider, `SessionLocal` patched onto a tmp DB); save-reconcile (stable id across
  re-extraction); graph compilation; and a full **end-to-end** on the Stub provider that drives a
  real compiled graph through the zero-images review pause and a `no_images` resume to two saved
  recipes — exercising checkpointer + interrupt + resume on one tmp SQLite file.

Decisions: keep LangGraph as-is (extraction is the one proven area carried over unchanged); httpx
over requests for v2 alignment; rate limit on `Config` (user-tunable), threads on `Settings`. Two
minor calls: the dedup prompt's non-breaking hyphen kept verbatim (a deliberate variant example —
`RUF001` ignored for that file), and lxml's compiled `etree` import suppressed for `ty`, both as
v1 did.

Green: backend `ruff` + `ty` clean, `pytest` **40 passed** (17 prior + 23 new). Frontend untouched
(its `make check` / `make test` need `npm install` in the worktree).

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

## 2026-06-01 — Recipes search page

The **Recipes** screen: a server-driven keyword search over the ~13k-recipe archive, **empty
until a query**. Deliberately **not** semantic/AI search (v1 had Gemini vector search; deferred
to a later slice) — this is substring + filters only.

- **Backend** `GET /api/recipes?q=&keyword=&book_id=&author=&sort=&limit=&offset=`: substring
  (`ILIKE`) across recipe name, keyword names, book title/author **and the JSON ingredients**
  (so an ingredient query like "anchovy" matches); keyword chips **AND-narrow** (each chosen
  keyword must be present, via `.keywords.any(...)`); `book_id`/`author` filters; `name`/`recent`
  sort; offset pagination; returns `{ total, items }`. **Filters count as a query** — a chip or
  book/author alone returns results; nothing set returns the resting empty state. `GET /api/keywords`
  feeds the filter chips (name + recipe count, popularity-ordered).
- **Frontend**: presentational `RecipesSearch.svelte` (search box · keyword chips · book/author
  selects · sort · result count · text-first rows · resting/loading/results/empty states · prev/next
  pager) + `RecipeRow.svelte` (name · right-aligned book·author · rotating-tint chips; **no leading
  number, no thumbnail** per DESIGN §5). The component owns its live criteria and emits `onSearch`;
  the `/recipes` route owns fetching (debounced text, monotonic-sequence guard against stale
  responses) and loads books+keywords on mount. Added the **Recipes** nav link.
- **DESIGN.md**: removed the **numbered-index-row** styling (the clay zero-padded `001` counter on
  list rows) per direction — rows are now plain text-first rows; method *step* numbers are kept.
  Recorded that the search screen is empty until a query.
- **Harness**: `recipes-search` verify unit — fixtures for resting/results/no-results, `act`
  fixtures (type query, toggle chip), a long-unicode-name probe, and the `expectFail` sentinel;
  invariants over the `data-verify-*` contract. Wire contract pinned both sides
  (`contract/recipes.example.json`, `keywords.example.json`).
- **Integrated `v2`** after book-detail landed: reconciled `schemas/recipe.py` (kept their
  `RecipeRow` index model alongside the search models), the test seed (Recipe 0 now carries both
  the `Pasta`/`Quick` keywords and an ingredient), and the home keyword count. No code dependency
  on book-detail; its `/books/:id` route now backs the row's book link. Both pages link to a
  `/recipes/:id` detail route that doesn't exist yet — a shared follow-up.

Green: backend `pytest` 33, `ruff`/`ty` clean; frontend `vitest` 25 (matrix 17), `svelte-check`
0/0. Verified via Playwright (1280×800 + 390×844): resting prompt, results with count + rows +
chips, AND-narrowing (chicken 1713 → +Quick 297), no-results state, mobile row reflow (source
wraps under the name). Fixed two issues found in the pass: a duplicate native `type=search` clear
button (hidden via `::-webkit-search-cancel-button`), and the keyword chip block pushing results
below the fold on mobile (capped the chips to 18; rarer keywords remain reachable by typing).

## 2026-06-01 — Keyword co-occurrence facets

**Goal:** make the keyword chips *contextual* — when a search is active, show the keywords that
most often co-occur with the current criteria (so clicking a chip re-ranks the rest to what
narrows further), instead of a fixed global top-N.

**Interpretation:** **data** co-occurrence — keywords appearing on the recipes that match the
current filters — not user-behaviour (no selection-history tracking).

- **Backend**: folded `facets` into the `GET /api/recipes` response (`{ total, items, facets }`)
  rather than a second endpoint — the search already computes the matching set, so facets are one
  more aggregation over it. Extracted the AND-narrowing filter into a shared `_search_conditions`
  helper used by the total, the rows **and** the facets. Facets = top-`FACET_LIMIT` (24) keywords
  by count over the filtered recipe ids, **excluding already-selected keywords** (every match
  carries them); their `recipe_count` is the count *within the current set*, so it shrinks as you
  narrow. `GET /api/keywords` is unchanged and now serves only as the **resting-state** global list.
- **Frontend**: the `/recipes` route caches the global list on mount, swaps the chips to
  `data.facets` on each active search (guarded by the existing monotonic `seq`), and restores the
  global list when cleared back to resting. `RecipesSearch.svelte` derives the displayed chips as
  **pinned selected keywords first** (pressed, no count — they're already chosen) then the facets,
  capped at 20 so the block stays a roughly constant height. Pinning keeps a selected chip
  deselectable even after it drops out of the server's facet list.
- **Harness**: new `facet-narrowed` fixture (a selected keyword absent from the facets) + a
  `facet-pins-selected` invariant asserting it's pinned first, pressed, and that no facet chip is
  pressed; added a `data-verify-chips` contract attribute (the rendered chip names, in order).
  Wire contract bumped both sides (`recipes.example.json` gains `facets`; Zod
  `recipeSearchResultsSchema` gains the array).

**Decisions:** pinned (already-selected) chips render **without a count** (every result carries
them — the number would just equal the total). Accepted chip reflow on selection rather than
reserving a fixed-height block; pinning + deterministic order (count desc, then name) keeps a
stable anchor.

Green: backend `pytest` 36 (+3 facet tests), `ruff`/`ty` clean; frontend `vitest` 25, matrix all
PASS, `svelte-check` 0/0. Verified via Playwright (1280×800 + 390×844) on real data: `chicken`
(1713) showed contextual facets (Main 1145, Chicken 730, Chinese 334, Quick 297…); selecting
**Quick** (→ 297) pinned it first and re-ranked the rest to the chicken+Quick set (Main 216,
Chicken 139, Chinese 75…) with Quick dropped from the facet list. Mobile chip block stays ~5 rows,
results remain near the first fold.

## 2026-06-01 — Keyword block prominence, clear button, random default sort

**Goal:** make the keyword facets the primary way to explore the archive (more prominent, more of
them), let the selection be cleared in one click, and default the result order to **random** so the
archive feels alive rather than alphabetised.

- **Prominence**: the keyword chips moved into a labelled `.keywords` section — a `KEYWORDS`
  header (darker/larger than the standard control label) over a 2px top rule, with slightly larger
  chips. The backend now hands over a generous pool (`FACET_LIMIT` and the route's global slice
  both **50**); the component renders them all and **clamps the block to 4 rows by measurement** —
  it reads each chip's row via `getBoundingClientRect`, clips the overflow rows (`overflow:hidden`
  + a measured `max-height`) and marks them `inert` (out of tab order / a11y tree), re-measuring on
  width change (`ResizeObserver`, width-guarded to avoid feedback) and on `document.fonts.ready`.
  Variable-width chips mean a fixed count can't hit a line target; measuring does, and it adapts to
  viewport (≈9 chips/row desktop, ≈3 mobile, always 4 rows). No layout (jsdom/SSR) → nothing
  clipped, everything shows. This deliberately reverses the earlier "cap at 18" call — the keywords
  now lead but stay bounded.
- **Clear selection**: a `Clear selection (n)` text button in the keyword header (shown only when
  something is selected) empties `selected` and re-searches; it disappears once empty.
- **Random sort, seeded**: added `random` to the sort options (now the **default**, ahead of
  Name/Recently-added). To keep pagination coherent, random is a **seeded deterministic shuffle**,
  not `ORDER BY random()`: the order key is `(recipes.rowid * multiplier) % 2147483647` (prime
  modulus → bijection, no ties), where `multiplier = 1 + (seed * 2654435761) % (MODULUS-1)` mixes
  the seed via Knuth's multiplicative hash so even small/adjacent seeds land large and well-spread.
  The frontend mints a fresh seed only when a *new* search starts (not on prev/next), so one result
  set keeps one ordering across pages. `seed` is a request param (`?sort=random&seed=…`); the
  response contract is unchanged. This reproducible total order is also the foundation for a future
  recipe-detail next/previous (still needs criteria+seed in the URL and a neighbours lookup).
  - **Bug caught in testing**: the first multiplier (`≈ seed`) was too small — with only ~13k rows,
    `rowid * multiplier` never exceeded the modulus, so it never wrapped and every small seed
    collapsed to plain rowid order (seed 42 == seed 99). The Knuth-hash multiplier fixed it.

**Tests/harness**: `clear-selection` fixture + `clears-selection` invariant (selection empties, no
chip pressed, button gone); backend `test_sort_name`/`test_default_sort_is_random`/
`test_random_sort_is_stable_per_seed`; pagination test pinned to `sort=name` for determinism.

Green: backend `pytest` 38, `ruff`/`ty` clean; frontend `vitest` 25, matrix all PASS,
`svelte-check` 0/0. Verified via Playwright (1280×800 + 390×844): prominent KEYWORDS block with ~40
facets, clear button appears/clears correctly, Random is the default and results are shuffled;
seeded pagination confirmed over real data (seed 42 pages disjoint and stable on refetch; seeds
42/43/99 give distinct orderings).
## 2026-06-01 — Recipe detail page (basic reading view)

Lands the `/recipes/{id}` route the book-detail recipe index already linked to (its rows
pointed at `/recipes/${id}`, previously dead). Scoped deliberately **basic, to extend later**:
no favourite / add-to-list / check-off / prev-next / keyword-search features (the masthead
keeps **Add to list / Action** no-op placeholders for them), and **no image serving yet** —
`has_image` is reported but the page is text-only for now.

- **Backend:** `GET /api/recipes/{id}` → `RecipeDetail` (schemas/recipe.py, beside `RecipeRow`):
  recipe fields (name, description, ingredients, instructions, yields, keywords sorted) + book
  provenance (book_id / title / author / has_cover) + `has_image` (= `image is not None`; serving
  the in-EPUB image is a later slice). `selectinload(keywords)` + `joinedload(book)`; 404 on
  unknown id. New `app/api/recipes.py`, registered in `router.py`. Pinned both-sides via
  `contract/recipe.example.json` (test_contract.py model + endpoint-keys; frontend
  contract.test.ts accept + drift). `test_recipes.py` (shape, content, provenance, optionals-null,
  404); the conftest seed's "Recipe 0" gained full content + an image path.
- **Frontend:** presentational `RecipeDetail.svelte` (`data-verify-unit="recipe-detail"` with
  `id / ingredients / steps / keywords / has-image`), the `/recipes/[id]` route
  (onMount→`fetchRecipeDetail`→3-state, snake→camel), `fetchRecipeDetail` + Zod. Reuses
  `lib/html` (Calibre-HTML→text) + `lib/title`.
- **Layout (iterated live with the user):** breadcrumb (carries book · author, so no kicker);
  a full-width **masthead** — large serif-italic title with the **Add to list / Action**
  placeholders pulled to the top-right, tinted keyword chips, a mono yield line, and the
  description as a serif **lede** (≤50rem) that clamps to 4 lines behind a **Read more / Read
  less** toggle once it passes ~360 chars (book-detail's pattern); then a **two-column body** —
  an ingredient-list rail beside a **wide numbered method column** (clay mono step gutter) that
  uses the desktop width — and a quiet full-width **From the book** provenance footer. No image
  callout, no metadata ledger. Mobile stacks the columns and the actions become a row.
- **Verify:** fixtures `populated / image-in-source / no-keywords / minimal / long-description /
  read-more-expanded` (the last drives the toggle via an `act: click`) + a `long-content`
  **probe** + the `contract-lie` **expectFail** sentinel; invariants on id, title,
  ingredient/step/keyword counts, sequential zero-padded step numbers, lede presence, the
  read-more collapsed/expanded states, the `has-image` contract flag, and the book back-link.
  `make verify` / `make check` / `make test` all green; Playwright at 390 / 1280 / 1536 across
  fixtures and real recipes (with-image, long-blurb, and no-/minimal-description) — zero
  horizontal overflow.
- **Dev tooling:** `frontend/vite.config.ts` now reads `VITE_DEV_PORT` / `VITE_API_PROXY`
  (defaults unchanged at 9789 / 9788) so worktrees can run dev servers side by side.

## 2026-06-01 — Recipe prev/next + navigation context

Ported v1's "where did I come from" navigation — the recipe page now pages through its **source
ordering** with previous/next and ←/→ keys — re-implemented cleanly for the v2 stack rather than
copying v1's query-string machinery. Like v1 it stays **stateless + URL-driven**: the recipe URL
carries `?context=<ordering>` and the page resolves the neighbours from it. Only **book order** is
wired today (search/list contexts arrive with those pages); an unknown context falls back to book
rather than 404.

- **Backend:** `GET /api/recipes/{id}` gained `context` (echoed, validated against
  `SUPPORTED_CONTEXTS`) plus `previous`/`next` (`RecipeNeighbour` = id + name, null at the ends),
  computed by `Recipe.order` within the book (one small ordered query each way). The contract
  example + `test_contract.py` were updated; `test_recipes.py` covers first/last/middle and the
  unknown-context→book fallback.
- **Frontend:** the breadcrumb row became a `.topbar` — breadcrumb left, a **prev/next pager on
  the right** (desktop; clay arrows, grotesk labels), each link carrying the context in its href.
  The `/recipes/[id]` route reads `?context`, reloads via `$effect` when the id/context changes
  (prev/next reuses the same route component), and a window `keydown` handler pages with **←/→**
  (ignored while typing in a field). `fetchRecipeDetail(id, fetch, context)` + Zod
  `recipeNeighbourSchema`.
- **Verify:** `data-verify-context/prev/next` contract; `first-in-source` / `last-in-source` /
  `only-recipe` fixtures with `pager-context` / `prev-link` / `next-link` invariants (a link
  appears iff that neighbour exists, and its href carries the id + context). `make verify` /
  `check` / `test` green; Playwright confirmed ←/→ **and** the click links page in book order on
  the live page (Spiral Curry Puffs ⇄ Prosperity Toss Fish Salad) and that the ends hide the
  spent arrow.

Book-detail still links recipes without an explicit context param, so arriving from it uses the
default book context — the correct ordering anyway. Search/list links will pass
`?context=search|list` and the endpoint grows those branches when those pages land.

## 2026-06-01 — Recipes search: URL-driven state (restore on back)

Bug: the `/recipes` criteria (query, selected keywords, sort) lived only in component state, so
opening a recipe and pressing **back** reset the search to empty. Fix: make the search URL-driven.

- The `/recipes` route **seeds the controls from the URL** on mount and writes the live criteria
  back with `replaceState` on every search — one history entry that updates in place, so clicking a
  recipe pushes a new entry and browser-back returns to the criteria-bearing URL. Search URLs are
  shareable now too.
- `criteriaFromParams` / the now-exported `criteriaToParams` round-trip `SearchCriteria` ↔ query
  params (`q`, `keyword[]`, `book_id`, `author`, `sort`, `seed`, `offset`; the constant page size is
  dropped from the URL). `RecipesSearch` already accepted a `criteria` prop, so it seeds unchanged.
- Subtlety caught via Playwright: on a client **back-navigation** the `$app/stores` `page` lags a
  tick behind the real URL, so seeding from `$page.url` restored an *empty* search even though the
  route remounted. Read `window.location.search` at mount instead (the browser's synchronous truth),
  falling back to `$page.url` when there's no `window`.
- Verified end-to-end: search *chicken* + select *Quick* → open a recipe → browser back restores the
  query, the pressed *Quick* chip, the co-occurrence facets and the 297-result list. `make check` /
  `test` / `verify` green.

Still book-order only on recipe detail: search-order prev/next + a "back to search" breadcrumb (the
`context=search` branch) is the remaining follow-up.

## 2026-06-02 — Recipe prev/next follows search order (context=search)

Wired the `context=search` branch promised above: a recipe opened from the Recipes search now pages
through the **search result order** (filters + sort + seed), not its book order, and the breadcrumb
links back to that search.

- **Backend:** `GET /api/recipes/{id}` also accepts the search params (`q`, `keyword[]`, `book_id`,
  `author`, `sort`, `seed`); for `context=search` it re-runs the same filtered + ordered query
  (shared `_search_order` helper, so the order matches the result page exactly), indexes the recipe
  and returns its neighbours — `None` at the ends or if it isn't in the set. `search` joins
  `SUPPORTED_CONTEXTS`; unknown contexts (e.g. `list`) still fall back to book. Tests cover
  search-order neighbours and that filters shrink the set (Recipe 0 alone under a Pasta filter → no
  neighbours, vs a next in book order).
- **Frontend:** search rows carry the criteria into their link (`searchContextQuery` →
  `/recipes/{id}?context=search&q=…&sort=…&seed=…`); the detail route forwards the whole query
  string to the API, derives the `contextQuery` the pager and ←/→ carry forward, and a `searchHref`
  back to the search. The breadcrumb is **context-aware**: `Recipes › Search results › {name}` (the
  "Search results" crumb links to the originating search) for search, the `Books › Author › Book`
  trail otherwise. `fetchRecipeDetail` takes the raw context query string.
- **Verify:** a `search-context` fixture + a `search-breadcrumb` invariant; `prev-link`/`next-link`
  now assert the pager href carries the full `contextQuery`. Playwright on real data: searching
  *chicken* by name, opening result #3, the pager's prev/next are results #2 and #4 (search order,
  ≠ book order), the breadcrumb links back to the search, and **→** advances to #4 keeping context.

## 2026-06-02 — Snappier recipe prev/next

Navigation felt laggy next to v1's HTMX. Two causes, both fixed:

- **Search-order neighbours re-ran the whole search on every arrow press** (~300ms: a `LIKE` scan
  over 13k recipes' JSON ingredients, ordered, all ids fetched). Added a small process-global **LRU
  cache** of the ordered result ids keyed by the exact criteria + seed, so stepping through one
  search computes the order once (~300ms) then costs ~4ms/step. Cleared per test (an autouse
  fixture, since it's module-global); re-extraction can leave an entry stale until eviction or a new
  seed — acceptable for a single user.
- **A loading flash on every navigation**: the route set `status='loading'`, tearing the recipe
  down to a "Loading recipe…" message before the next rendered. Now the current recipe stays on
  screen until the next arrives, then swaps (like an HTMX partial) — the loading state shows only on
  a cold start. A monotonic `seq` guard drops superseded fetches, and `{#key recipe.id}` remounts
  per recipe so component-local state (cover-failed, read-more) resets, but only once the new data
  is in.

Result (Playwright, real data): arrow-key nav through a *chicken* search is **~30ms/step with no
loading flash** (was ~300ms + a teardown/rebuild); book-order nav (already ~5ms) also loses the
flash.

## 2026-06-02 — "Browse recipes" from a book → book-ordered search

The book-detail sidebar's second action was a placeholder ("Action"). Made it the real **Browse
recipes** action: it opens the Recipes search pre-filtered to that book and sorted in book order.

- **Backend:** added a `book` sort to `GET /api/recipes` (and the shared `_search_order`, so
  prev/next would follow it too). Filtered to one book it's the recipe's stored `order`; unfiltered
  it groups by book (`Book.title`, then `order`). `_search_order` now returns a list of ORDER BY
  clauses (splatted at both call sites) so the book case can carry the title + sequence pair. Test:
  book-filtered `sort=book` returns the recipes in stored order.
- **Frontend:** `SortKey` and `criteriaFromParams` gained `'book'`; the sort `<select>` gained a
  "Book order" option. The book-detail action is now an `<a class="btn ghost browse">` →
  `/recipes?book_id={id}&sort=book` (a real link, not a button, so it routes/middle-clicks), shown
  only when the book has recipes. The old placeholder's `.ico` style and unused SVG are gone.
- **Verify:** `browse-link` asserts the href is `/recipes?book_id={id}&sort=book` on populated
  fixtures; `browse-hidden-when-empty` asserts the zero-recipe book offers no link. Playwright on
  real data: *West Winds* (136 recipes) → **Browse recipes** lands on `/recipes` with the book
  filter + "Book order" selected, *1–30 of 136* in book sequence; the empty-book state shows only
  "Read book".

## 2026-06-02 — Faster keyword chips on the Recipes page

The keyword block lagged on a hard refresh. Two causes, on real data (~13.4k recipes, ~78k
recipe-keyword links, **4,968** distinct keywords):

- **No index for the group-by.** `/api/keywords` and the search facets group `recipe_keywords` by
  `keyword_id`, but the only index was the `(recipe_id, keyword_id)` PK — useless for a `keyword_id`
  group-by, so SQLite rebuilt a *transient* index on every call (`EXPLAIN`: "USING AUTOMATIC
  COVERING INDEX"). Added a standing index `ix_recipe_keywords_keyword_id` (declared on the
  association `Table`, so `create_all` gives the tests it too; migration `c4867b517317` for real
  DBs). Aggregation dropped ~270ms → ~110ms.
- **Shipping the whole corpus.** The endpoint returned all 4,968 keywords (~190KB) though the client
  renders only the most-used ~50 (`.slice(0, 50)`), so it parsed ~5,000 Zod objects per load. Added
  a `limit` (default 50, ≤500) to `GET /api/keywords`; `fetchKeywords(50)` requests it and drops the
  client slice.

End to end the endpoint went **~425ms → ~178ms** and the payload **~190KB → ~1.9KB** (50 rows);
the top chips are unchanged (Main 4617, Vegetarian 3337, …). Tests: `?limit=1` returns the single
top keyword; the existing exact-list assertion still holds (under the cap).

## 2026-06-02 — Dark mode ("Midnight")

Added a light/dark theme that **defaults to the OS preference** and is overridable from a toggle in
the top-right of the nav. The whole app already routed colour through CSS custom properties, so the
theme is essentially one override block.

**Ground choice.** DarkReader was auto-darkening the warm-ivory site into a muddy brown. Rather than
fight the extension, we ship a real dark theme so it backs off. Mocked four candidate grounds (slate
/ graphite / midnight / warm-stone) in a standalone switchable HTML preview rendered in the actual
design language; picked **Midnight** (`#14181e`) — a cool blue-black that reads as slate, deliberately
**not** a tinted inversion of the ivory. Clay is preserved (nudged brighter to carry on the dark
field); chip tints lift with lighter labels; `--clay-deep` flips to a *lighter* clay since "more
contrast" means lighter on a dark ground. Full palette is in `DESIGN.md §3.1` and the
`[data-theme='dark']` block in `app.css`.

**Mechanics.**
- `theme.ts` — `preference` (`light`/`dark`/`system`, persisted to `localStorage` as `cookmarks-theme`;
  `system` = key absent) and `resolvedTheme` (what the icon reflects). `initTheme()` persists changes,
  applies `data-theme` to `<html>`, and follows the OS live while preference is `system`. `toggleTheme()`
  pins an explicit light/dark (drops `system`).
- A tiny inline script in `app.html` resolves the theme **before first paint** (no light-mode flash),
  mirroring `theme.ts`'s logic.
- `ThemeToggle.svelte` — presentational (props `theme` + `onToggle`), sun/moon icon, `aria-label`
  naming the *action*. Wired in `+layout.svelte`; ships its own verifiable unit
  (`theme-toggle.verify.ts`: light/dark fixtures, a rapid-click probe asserting `onToggle` fires
  without the controlled icon drifting, and the truthfulness sentinel).
- Replaced the two hard-coded `background: #000` primary-button hovers with a new `--ink-deep` token
  (`#000` light / `#fff` dark) so the hover stays correct under both themes.

**Gotcha fixed.** The toggle pushed the (not-yet-responsive) nav over 390px → 5px of horizontal
scroll (violates DESIGN §8). First fix didn't take: the mobile `.nav` override was authored *above*
the base `.nav` rule, so at equal specificity the base won. Moved it below the nav rules, tightened
the mobile gap to `1rem`, and set the toggle `flex: none` so it holds its 32px tap target. A proper
mobile drawer remains future work (pre-existing).

Verified: `vitest` 35/35 (incl. the new unit), `svelte-check` clean, and Playwright screenshots of
the books grid + recipe detail in both themes at 1280 and 390 — no overflow, light mode unchanged.

## 2026-06-02 — Recipes page: parallel loads + a lightweight books endpoint

The Recipes page loaded its data in a serial waterfall — `fetchBooks()` → `fetchKeywords()` →
the search — so the result list (the thing you actually want) waited behind two filter requests it
doesn't depend on. Over Tailscale that's three round-trips stacked. Profiling on real data: books
~57ms, keywords ~211ms, then the search.

- **Parallelised `onMount`.** The three requests now fire concurrently rather than via sequential
  `await`s, and the URL's search is restored immediately instead of after the filters resolve.
  Verified live (Playwright, real data): all three start within a **2ms** window; results render as
  soon as the search returns rather than after keywords.
- **Subtlety — `replaceState` before router init.** Firing the search straight away first surfaced
  as a silent regression: `run()` called `syncUrl()` → `replaceState()` as its first step, which
  throws *"Cannot call replaceState before router is initialized"* this early in mount, so the
  search never fired. (The old code dodged it only because `run()` ran after two awaited
  round-trips.) Split `run()` into `execute()` (pure search, no URL writes) and `run()` (syncUrl +
  execute); the initial restore calls `execute()` — the URL already reflects those criteria, so
  there's nothing to sync back.
- **Lightweight `GET /books/filters`.** The dropdown reused the rich `/books`, paying ~30ms to
  `COUNT` 13.4k recipes per book for counts it discards (the query plan was already optimal — it's
  just the inherent cost of aggregating). Added `/books/filters` → `{id, title, author}` only
  (~4ms, no count, no per-book cover stat), declared before `/books/{book_id}` so the literal path
  wins over the UUID matcher. `/books` keeps its counts for the home and library pages. New
  `BookFilter` schema + `contract/bookfilters.example.json` pinned from both sides.

Verify: `make check`, `make test` (55 backend incl. 2 new contract tests, 33 frontend incl. 2 new),
`make verify` matrix green. Live: with a `book_id` filter → 3 concurrent requests, search fires,
`status="results"`, no console errors; resting `/recipes` → books/filters + keywords only, 101
keyword chips, `status="resting"`.

## 2026-06-02 — Keep the verify harness off every page's critical path

A Chrome HAR of `/recipes` showed the API calls didn't start until ~224ms in — not network, but module loading. `onMount` couldn't fire until a cascade of ~80 modules resolved, including the **entire verify harness and every page's components** (`home-landing.verify.ts`, `BooksLibrary.svelte`, …) on the recipes page.

**Root cause.** The root `+layout.svelte` installs `window.__verify` via a *static* import chain: `handle.ts` → `runner.ts` → `registry.ts` → `import.meta.glob('/src/**/*.verify.ts', { eager: true })` → every unit → every component. So loading any page eagerly loaded the whole harness. A prod build confirmed it wasn't dev-only: node 0 (the layout, on every page) statically imported a **37 KB chunk** of verify tooling — shipped to every visitor on first paint.

**Fix.** Made `handle.ts` import `./runner` **dynamically**, inside the `manifest`/`runAll` closures, rather than at module top. The layout still installs `window.__verify` everywhere, but the registry (and its glob over all units + components) loads only when verification is actually invoked — or when a `/verify` route is visited, since those routes import the runner directly. `VerifyHandle.manifest` is now async (like `runAll` already was); nothing in the app or the matrix calls it — only a live agent does.

**Verified.** Prod build: the 37 KB registry+units bundle is no longer statically reachable from the layout — it's reached only via a dynamic `import()` (code-split). Dev (Playwright, warm): the recipes page loads **0** verify/cross-page modules (was ~30+), and the first API call starts at **~116ms** instead of ~224ms. Harness still works: `window.__verify.runAll()` on a normal page dynamically loads and returns 37 PASS + the 5 `expectFail` sentinels; the `/verify` dashboard renders "42 fixtures · 37 pass · 5 fail". `make check`/`make test` (55 backend, 37 frontend)/`make verify` all green.

## 2026-06-02 — Cache the global most-used keywords

`GET /api/keywords` (the resting-state filter chips) spent ~170ms grouping a count over 4,968 keywords against 78,334 `recipe_keywords` links and sorting all of them to take the top 50 — on every request, for a result that's identical until the corpus changes. The query plan was already optimal (it uses `ix_recipe_keywords_keyword_id`); the cost is inherent to recomputing the aggregate, which `LIMIT` can't prune.

**Cache.** A module-global, computed-once-per-process cache of the top `_KEYWORD_CACHE_CAP` (500) keywords, sliced per request — the ordering is fixed (count desc, then name), so any `limit ≤ cap` is a prefix. Mirrors the existing `_SEARCH_ORDER_CACHE` pattern in the same module, with a `_clear_keyword_cache()` hook. The endpoint's `limit` ceiling is now bound to the cap so a slice always satisfies it. Test isolation: the autouse `_reset_caches` fixture clears it (alongside the search-order cache) so each test's fresh DB never reads a previous test's keywords.

**Invalidation.** Today only the import script (a separate process) and, later, the extraction task write keywords — so a running server's cache is never stale mid-life in the current scaffold. The extraction task will call `_clear_keyword_cache()` on write when it lands (in-process); if it ends up cross-process, the fallback is staleness-until-restart (consistent with how `_SEARCH_ORDER_CACHE` already behaves) or a TTL. Keyword "popularity" chips are approximate by nature, so this is tolerable — which is why the cache was chosen over denormalising a `recipe_count` column.

**Verified.** New test pins the contract: a keyword added after the first call isn't reflected until `_clear_keyword_cache()`. Live on real data (192 books / 13.4k recipes / 4,968 keywords): first call **184ms** (computes top-500), subsequent calls **~1.5ms** (cache hit); top chips unchanged (Main 4617, Vegetarian 3337, Quick 2882), and `limit=5` is a true prefix of `limit=50`. `make check` (backend) + `pytest` (56 passed, +1) green.

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

## 2026-06-02 — Extraction eval suite (task-first) + pipeline model/method controls

A professional rebuild of v1's rudimentary `_eval/run_eval.py`, plus the pipeline controls it needs.
The eval is organised **by task** (pipeline role): for each task, candidate models run against the
gold books that exercise it and are scored, so you can pick the cheapest-good model *per task* rather
than pin one model everywhere. (v1's eval *thought* it picked a model via `config.gemini_model`, but
nothing read that field and it never set `report.model_name` — so every v1 run silently used the
per-role defaults. v2 does it for real.)

**Pipeline controls** (production-useful, not just eval scaffolding):
- **Per-role model override** — `Config.model_overrides` (`{ModelRole value: model}`), consulted by
  `AIProvider.model_for()`; `registry.get_ai_provider` threads it through. One task can use a
  different model while others keep provider defaults. Migration `b9d0832aaea4`.
- **Image-match override** — `check_if_can_match_images(model=...)`; `analyse_epub` passes the run's
  model so a pinned model drives block-vs-file routing too.
- **Force method** — `analyse_epub` honours a pre-set `run.images_can_be_matched`, skipping the
  fallible check. The eval pre-sets it to run a book straight through blocks.
- **Accurate method recording** — `extract_file`/`extract_block` now stamp `extraction_method`, so a
  file→review→block run no longer mis-reports `file`.

**Eval suite** `backend/evals/` (CLI `python -m evals run|report`, `make eval`):
- `matching.py` — name-based match (exact then rapidfuzz fuzzy) with recipe-set precision/recall/F1,
  catching misses *and* hallucinations that v1's order-matching could not.
- `metrics.py` — per-field Jaccard (+missing/+extra), name/yield/image(by-basename)/keywords, a
  renormalised composite. The scoring layer is app-free and unit-tested without a DB.
- `environment.py` — isolated `eval.sqlite3` (current ORM schema), books resolved from the Calibre
  library, key from env→app-DB, pipeline rebound onto it; prod data untouched.
- `runner.py` — per task → candidate → book; pins the candidate via `model_overrides`, forces block
  for the blocks task, captures cost/tokens/method/latency, scores, writes artefacts.
- `report.py` + append-only `index.jsonl` ledger (git-friendly, one row per run/task/model/book,
  stamped with `git_sha`); per-task leaderboards + a `task` history view.
- `eval.toml` — three tasks over the v1 gold books: many-per-file→craveable, one-per-file→curry-guy,
  blocks→nothing-fancy (forced).

A first real run (single all-flash, pre-rebuild) already paid off: the eval caught the image-match
model **misrouting nothing-fancy** — a 273-chapter wasted file pass before falling through review into
blocks, most of its $1.25 — which is exactly why the blocks task forces the method.

Decisions: rapidfuzz added as an `eval` dependency group (synced by default so `make check`/`test`
cover evals); the ledger is committable history while bulky per-run artefacts under `runs/` are
gitignored; `eval.sqlite3` is throwaway.

Green: backend `ruff` + `ty` clean, `pytest` **62 passed** (40 prior + 22 new); full task-first path
validated offline on the Stub provider (incl. forced block) before any billable run.

## 2026-06-02 — Read a book as an EPUB (in-app reader)

A book can now be **read as an EPUB** in-app, from a new "Read epub" action on the book detail
page. The EPUB files already sit on disk in the Calibre library (the same place covers come from),
so this is mostly plumbing them to a browser renderer.

**Decisions.** Renderer is **foliate-js** (the engine behind Foliate; MIT). It's not on npm and
upstream's unstable, so it's **vendored as a pinned copy** under `frontend/src/lib/vendor/foliate-js/`
(commit `78914ae`; `PROVENANCE.md` records source + the two deviations) rather than a submodule —
this project develops in git worktrees, where submodules are awkward, and a committed copy needs no
init step. The 11 MB `pdfjs` is omitted and `pdf.js` replaced with a stub: we read EPUB only, and
`view.js` imports `pdf.js` solely for files that sniff as PDF. **Out of scope (deliberately):**
reading-position/bookmark persistence (opens at the start each time) and recipe→EPUB-location
deep-linking (no data for it yet).

**Backend.** `app/epub.py` (`epub_path`/`has_epub`, mirroring `covers.py`) globs `*.epub` in the
book's Calibre dir. `GET /api/books/{id}/epub` streams it (`application/epub+zip`) with the same
path-traversal guard as the cover route. `has_epub` is added to `BookDetail` **only** — not the
library list, which would stat the filesystem ~192×.

**Frontend.** Split for verifiability: **`ReaderChrome.svelte`** is presentational (top bar ·
progress · page nav · slide-in TOC drawer · font-size · theme toggle) with a `data-verify-*`
contract and a full verify unit (`reader-chrome`, 8 fixtures incl. probe + sentinel). **`EpubReader.svelte`**
is the effectful half: mounts `<foliate-view>` in `onMount`, fetches the EPUB as a named `File`
(not a bare Blob — foliate's loader sniffs the filename), opens it, builds the TOC, wires prev/next
+ arrow keys, and tracks progress via the `relocate` event. New immersive route `/books/[id]/read`;
the root layout's `showChrome` now also suppresses the global nav/footer on `/read` (alongside the
existing `?chrome=0`).

**Relaxed verifiability (per CLAUDE.md).** The effectful reader can't run in the jsdom matrix
(iframe rendering, a third-party engine), so `ReaderChrome` carries the harness contract and
`EpubReader` is verified live (below). `EpubReader` composes the verified chrome.

**Theming.** The book's content lives in a cross-document iframe, so the app's CSS variables don't
reach it — `EpubReader` injects concrete colours (DESIGN tokens) via `renderer.setStyles`, re-applied
on theme/font-size change. Dark mode forces text colour + transparent backgrounds with `!important`,
because the book's own stylesheet wins on specificity (without it, text stayed dark-on-dark).

**Tooling.** Vendoring an untyped JS engine meant turning `checkJs` off in `frontend/tsconfig.json`
(the project is TS/Svelte — it has no first-party JS to lose checking on) and excluding the vendor
dir from the program; first-party types + a loader live in `src/lib/reader/foliate.ts`, so our own
code stays fully typed.

**Known limitation.** foliate-js requires a CSP blocking scripts to be safe against EPUBs with
embedded JS; we don't set one yet. The library here is the user's own trusted, single-user
self-hosted Calibre collection, so the risk is low — a CSP on the static/app responses is a sensible
follow-up.

**Verified.** `make check` (ruff + ty + svelte-check, 0 errors), `make test` (61 backend incl. epub
endpoint + `has_epub` tests; 41 frontend), `make verify` matrix green (incl. `reader-chrome`),
`make build` resolves the vendored dynamic-import graph (incl. the pdf stub). Live (Playwright on
real data, "1,000 Indian Recipes"): book detail shows "Read epub"; the reader parses the EPUB (26
sections, 22 TOC entries), renders the cover then reflowable two-column text, the TOC drawer lists
all 22 entries with the current one in clay, light/dark themes both read well (dark text now forced
legible), and the layout reflows to one column at 390px. No console errors.

## 2026-06-02 — Lists: favourites + custom collections, end to end

The first feature built on top of the read-only slices: the full **Lists** vertical — a
default **Favourites** plus arbitrary named collections, a Lists index, a list-detail index, the
favourite ★ on a recipe, and an add-to-list control. Models (`RecipeList`/`RecipeListItem`) already
existed from the initial schema, so no migration; this slice wired the API, the wire contract, the
components/verify units, the routes, and the recipe-detail integration.

**Backend** (`app/api/lists.py`, `app/schemas/recipe_list.py`). Endpoints: `GET/POST /lists`,
`GET/PATCH/DELETE /lists/{id}`, `POST /lists/{id}/recipes` + `DELETE /lists/{id}/recipes/{recipe_id}`
(both idempotent), `GET /recipes/{id}/lists` (membership map for the picker), and
`POST /recipes/{id}/favourite` (toggle). The default Favourites list is created lazily by
`get_or_create_favourites()` from the list reads — mirroring v1's `get_favourites` — so it always
exists even on a fresh DB; this is a deliberate write-on-read, acceptable for a local single-user
app and the only way to honour DESIGN's "a default Favourites" without a startup hook or seed
dependency. Guards: the default list rejects rename/delete with **409**. Lists order with the
default pinned first, then by name. `RecipeDetail` gained `is_favourite`, computed by a *pure* read
(`_is_favourite`, never creates the list) so an unstarred recipe on a fresh DB reads `false`.

**Wire contract.** The deliberate three-step edit: `is_favourite` added to `recipe.example.json` +
the Pydantic model + the Zod schema; new `listsummary`/`listdetail`/`listmembership` examples pinned
from both sides (`test_contract.py` model-dump + endpoint-key assertions; `contract.test.ts`
accept-the-example + reject-a-drifted-field). `test_lists.py` covers create/rename/delete, the
default guards, membership idempotency, the favourite toggle, the membership map and the 404s.

**Frontend.** Four presentational components, each with a co-located `*.verify.ts`
(`favourite-toggle`, `add-to-list`, `lists-index`, `list-detail`): a real `button[aria-pressed]`
star; a disclosure picker (membership toggles + inline create); a searchable card grid (Favourites
pinned, "Default" badge, no rename/delete on it); and a list index of removable recipe rows.
`RecipeRow` grew an optional `onRemove` (renders a labelled Remove button only when passed, so
search/book-detail usage is untouched). Action controls use explicit `onclick` + Enter-key handlers
rather than `<form onsubmit>` + a submit button, so the harness's `click()` drives them
deterministically under jsdom. Routes `/lists` and `/lists/[id]` do the fetching; `recipes/[id]`
wires the ★ + picker (creating a list from the picker also adds the current recipe, as v1 did);
the nav gained a **Lists** item.

**Pre-existing bug found via live network inspection.** Driving the recipe page in Playwright, the
network showed `/api/recipes/{id}` and `/api/recipes/{id}/lists` each fired **8,182×** — a
render→fetch feedback loop. The route's `$effect` calls `load()`, whose synchronous prefix reads
`recipe` (`if (!recipe) …`), and `load()` then reassigns `recipe`; because the write lands in a
microtask after `await`, Svelte's synchronous depth-guard never trips, so the effect re-triggered
itself forever (silent — the page still rendered). `git show v2:` confirmed the trunk route is
structurally identical, so the loop **predates this work**; the new membership fetch merely rode
inside it and made it visible. Fixed by wrapping the `load()` call in `untrack()` so the effect
depends only on the route id + query string.

**Mobile nav overflow.** The fourth nav item (Lists) tipped the single-row nav past 390px
(`scrollWidth` 410 > 390), violating DESIGN §8 "no horizontal scroll". Added a `≤480px` rule
tightening the gap and trimming the wordmark/links so it stays single-row (a proper drawer remains
future work).

**Verified.** `make check` (ruff + ty + svelte-check, 0/0), `make test`/`make verify`
(82 backend incl. the new lists + contract tests; 58 frontend incl. the four new units' matrix
fixtures), all green. Live on real data (Playwright): `/lists` shows Favourites (★, "Default", no
rename/delete) + custom lists with rename/delete; `/lists/{id}` lists removable recipe rows; the
recipe masthead shows the ★ and add-to-list, the picker opens with the correct membership
(Sauces ✓), and clicking Favourites persists to the backend (`Favourites:true`) and flips the star
to "Favourited". No horizontal scroll at 390px on any new screen. (Pixel inspection of the
screenshots wasn't possible — the Playwright browser is sandboxed from the host filesystem — so
verification was via accessibility snapshots, live interaction, overflow measurements and the
verify matrix.)

**Polish (same session, on review).** A few UX refinements after eyeballing the live pages:
- **Equal-height list cards.** The default Favourites card was taller because its ★ sat on its own
  line; moved the ★ inline before the name and made cards fill their grid cell (`height: 100%`) so
  every card in a row shares one height.
- **Recipe masthead order.** Favourite ★ now sits *above* Add-to-list (swapped the two in `.actions`).
- **Picker dismissal.** The add-to-list panel now closes on a click anywhere outside it (a capture
  -phase `pointerdown` listener attached only while open, ignoring clicks within the picker so list
  toggles and the create field keep working). Verified live: outside-click closes, toggle keeps open.
- **Create via modal.** The Lists index's inline "new list" textbox became a **New list** button that
  opens a centred modal (dim scrim as a labelled `<button>` for keyboard/a11y, focused name field,
  Enter/Escape, Cancel/Create). Its entrance uses a dedicated `modalIn` keyframe — `fadeUp`'s
  `transform: none` would otherwise clobber the `translate(-50%,-50%)` centring (caught in a
  screenshot: the dialog rendered off-centre until fixed). The `lists-index` verify unit's create
  fixture now opens the modal first; a new `open-create-modal` fixture asserts the dialog appears.
  `make check`/`make verify` green; no horizontal scroll at 390px.

## 2026-06-03 — Match recipes in the EPUB reader → in-page "save to favourites"

While reading a book, the reader now recognises which recipe a rendered title names and injects a
**save-to-favourites pill right next to that title** in the page. Builds on the EPUB reader + the
favourites API (both now on `v2`).

**Backend.** New lean `GET /api/books/{id}/recipe-index` → `[{id, name, is_favourite}]` for *every*
recipe in the book, in book order (the search endpoint caps at 100; the matcher wants the full set).
Favourite state is read from the default list, scoped to the book. New `RecipeIndexEntry` schema,
pinned both sides via `contract/recipeindex.example.json` (+ `test_contract` / `contract.test`).

**Matcher (`src/lib/reader/match.ts`).** Pure, dependency-free (so it unit-tests in plain vitest):
`normaliseTitle` (lowercase, strip accents/apostrophes, drop leading "Chapter N:"/numbering,
alphanumeric-collapse), `buildRecipeIndex` (by normalised name, first-wins), and `matchHeading`
(exact match, then a *guarded* whole-phrase prefix fallback for trailing qualifiers). It returns
null rather than guess — a wrong favourite is worse than a missed one. 15 unit tests.

**Reader integration (`EpubReader.svelte`).** Fetches the recipe index alongside the EPUB; on each
foliate `load` event it scans the section's content document and injects a clay `☆ Save` / `★ Saved`
pill after any line that names a recipe, wired to `toggleFavourite`. Key discovery from live
inspection: cookbook EPUBs (Calibre-converted) rarely use semantic headings — titles are **bold
lines** (`<p class="calibre1"><b class="calibre3">PIERINA'S CRESCIA SFOGLIATA</b></p>`). So
candidates are `h1–h6` **and** `b/strong`; cross-reference `<a>` links with the same text are
excluded; bold candidates require an *exact* name match (headings may use the prefix fallback);
nested duplicates are de-duped. The pill is injected into the same-origin content doc and styled via
the existing `setStyles` content-CSS (so it themes with light/dark and resists the title's
uppercase/italic).

**Verified.** `make check` (ruff + ty + svelte-check, 0 errors), `make test` (backend incl. the
recipe-index endpoint + favourite-reflection tests; frontend incl. 15 matcher + 2 new contract
tests), `make verify` matrix green, `make build` ok. Live (Playwright, *Pasta Grannies*): paged to a
recipe, the `☆ Save` pill appeared on the matched title, clicking it drove the Favourites list 4 → 5
and flipped the pill to `★ Saved`; cross-reference links got no pill.

**Limits / not done.** Matching is heuristic and title-markup-dependent (works on bold-line and
heading titles; books that style titles only via positioning/size won't match). No reverse link
(recipe → page) and no stored recipe↔location index — that remains future work. Reading position
still isn't persisted.

## 2026-06-04 — Similar recipes on the recipe page (embedding KNN + keyword fallback)

The recipe page now closes with a **"Similar recipes"** section — related recipes found by nearest-
neighbour over the imported Gemini embeddings. This is the **first read-consumer of the embeddings**
in v2, so it also lands the `VectorStore` port (CLAUDE.md previously deferred it to the search
milestone).

**Grounding the data first.** Queried the real imported DB: 13,403 recipes / 192 books, **99.0%
embedding coverage** (only 128 un-embedded), 3072-d float32 vectors, brute-force KNN ~149ms warm.
The load-bearing discovery: **`recipes.id` is stored un-hyphenated (`57c4ef06…`) but
`recipe_embeddings.recipe_id` is hyphenated (`1435bb15-…`)** — a raw join silently matches *nothing*.
The bridge is `str(uuid.UUID(x))`, confined entirely to the store.

**Decisions (re-thought from v1, which did a raw KNN strip of badge chips with no diversity/fallback):**
pure cosine KNN (no diversity rerank — same-book neighbours are allowed to surface); a **footer
section of editorial index rows** reusing `RecipeRow` (not v1's chips); computed **on demand** via a
**lazy endpoint** (`GET /api/recipes/{id}/similar`) the page fetches *after paint* (no AI call — the
recipe's own stored vector drives the KNN); a **shared-keyword fallback** for the ~1% with no
embedding.

**Backend.** `app/services/vector_store.py` — `VectorStore` bound to a session, self-creates the vec0
table `IF NOT EXISTS`, bridges the id formats, exposes `get_embedding` / `search` / `search_excluding`
/ `upsert`. New `GET /api/recipes/{id}/similar` → `SimilarRecipes {basis: 'vector'|'keyword', items:
[RecipeSummary]}`; `basis` records how the list was found (honesty/verification, not surfaced to the
reader). Pinned both sides via `contract/similar.example.json`. Factored a shared `_summary(recipe,
book)` builder out of `search_recipes`.

**Frontend.** `fetchSimilarRecipes` + Zod schema (optional `limit` — omit for the server default,
pass for a slice). The recipe-detail footer (`SimilarRecipes.svelte` — mono heading, hairline-ruled
`RecipeRow` list, designed empty state) requests a small slice of **5**, lazily after paint (guarded
by recipe id, reset on navigation), and when that comes back full renders a **"More like this →"**
link to a fuller browse view. That view — `SimilarBrowse.svelte` at **`/recipes?similar=<id>`**
(breadcrumb · serif "Similar to *‹recipe›*" heading · the full ranked list, server default of 30) —
the `/recipes` route branches into reactively on the `similar` param. Two verifiable units
(`similar-recipes`, `similar-browse`), each with probes + a designed empty state.

**Clean book titles.** `RecipeRow` now renders the **clean (pre-colon) title** via `cleanTitle`, so
every recipe list — similar, search, lists — drops Calibre subtitles ("The Wok: Recipes and
Techniques" → "The Wok"). It was the one title render that still showed the raw string.

**Verified.** Backend 144 pytest / ruff / ty clean; frontend 89 vitest (incl. contract tests) /
svelte-check / 53-fixture verify matrix green. **Live end-to-end against the real DB** (Playwright):
"Kara-age" returns karaage / Japanese-fried-chicken variants across many authors (`basis: vector`) —
genuinely strong semantic matching; the footer shows 5 + the link, `/recipes?similar=…` shows 30
ranked rows under "Similar to *Kara-age*". No console errors.

**Limits / not done.** Pure KNN means a recipe pulls its book-mates when a book has many similar
recipes (accepted, by choice). No precomputed neighbours table (the ~149ms KNN is off the critical
path); the browse view shows a single ranked page of 30 with no pagination. The search milestone
still owns query-embedding *generation* and the embedding write-path for new extractions; this slice
only *reads* the imported vectors.
## 2026-06-03 — AI (semantic) search on the Recipes page

Wired the long-stubbed embedding hook into a working **semantic search**, sitting alongside the
existing keyword/facet search on `/recipes` as a second affordance.

**Shape.** Embedding-only — no generative LLM in the hot path. A query is embedded once and matched
against recipe vectors by cosine KNN (sqlite-vec `vec0`); results come back ranked by distance. Each
recipe is embedded from `recipe_to_text` = name + keywords + ingredients (v1 parity, so the 13,275
Gemini vectors carried over by the import script are reused as-is — zero re-embedding).

**Provider abstraction.** Added `embed()`/`embed_batch()` + `embedding_model`/`embedding_dimensions`
to `AIProvider` (with an `EmbedTask.DOCUMENT|QUERY` hint). Only **Gemini** is wired now
(`gemini-embedding-001`, 3072-dim); **Stub** returns deterministic BLAKE2b hash vectors so search
runs offline in tests/dev; **OpenRouter** inherits the base `NotImplementedError`. The shape is ready
for more providers + a re-embed-on-switch flow, but that's deferred — the `vec0` width is fixed at
3072 and switching embedding models would mean a full re-embed.

**Service + endpoint.** `app/services/embeddings.py` is the embedding *generation* layer on top of
`app/services/vector_store.py` (the `VectorStore` that owns the vec0 table, shared with similar
recipes): `recipe_to_text`, `embed_recipes` (provider → `VectorStore.upsert`), `search` (embed the
query → `VectorStore.search`), `backfill` (over `VectorStore.embedded_ids`). `GET
/api/recipes/semantic?q&limit` returns
`SemanticSearchResults {available, query, total, items}` where each item is a `RecipeSummary` +
`distance`; declared before `/recipes/{recipe_id}` so "semantic" isn't parsed as an id.
`available:false` (no embedding-capable provider) is kept distinct from an available search that
matched nothing, so the UI prompts to configure a provider rather than implying the library is empty.
The extraction hook (`generate_recipe_embeddings`) now calls `embed_recipes`, so newly-extracted
recipes are searchable; `scripts/backfill_embeddings.py` fills any gaps.

Query embeddings are served from a small in-process LRU (256 entries, keyed by `(model, query)`), so a
repeated query — back-navigation, re-pressing AI search, a reopened shared URL — skips the provider
round-trip while the vec0 KNN still runs against live data (results never go stale). Measured on the
full library: a cold query ~690 ms (incl. the Gemini call) vs ~220 ms cached. The cost saving is
negligible at single-user volume — this is a latency/resilience win, not a cost one.

**UI — one box, two icon buttons.** After reviewing five layout mockups, settled on a single search
input on `/recipes` with two inline icon triggers: a **magnifier** (keyword, ink-filled) and a
**spark** — "AI search", clay-outlined: a single drawn 4-point star, not the emoji ✨ cluster, kept
restrained per DESIGN. Typing / Enter / the magnifier run the live keyword search; the spark runs the
AI search on the current text. The box owns a live `mode` (internally `keyword`/`semantic`); in AI-search
mode the keyword filters (book/author/sort/chips) fade back — they don't shape the results — but stay
live (touching one returns to keyword), and the count line reads "N results · most relevant first"
with no pager. `?mode=ai` in the URL restores AI-search mode. Results open recipes in book context (no
AI-search prev/next ordering — deferred), and the truthful unavailable state ("Semantic search needs an
AI provider configured.") shows when no provider can embed.

**Verified.** `make check` (ruff + ty + svelte-check, 0/0); 141 backend tests — new
`test_semantic_search` exercises the full HTTP endpoint + vec0 search with the stub provider
(exact-text ranks first at distance 0; unavailable without a provider; backfill embeds only what's
missing) — plus the contract pin (`semanticsearch.example.json`, both sides); 64 frontend tests incl.
the verify matrix's new `semantic-results` / `semantic-unavailable` / `switch-to-ai` fixtures. Live
end-to-end (headless Chrome on a seeded stub DB): `/recipes?mode=ai` ranks results with dimmed
filters, `?q=dal` does keyword search with facets, and the unavailable + 390px mobile states render
per DESIGN.

## 2026-06-05 — "Extracted only" filter on the Books library (MY-5)

The Books page (`BooksLibrary.svelte`) gained a checkbox in the controls bar that, when
ticked, narrows the grid to books with extracted recipes (`recipeCount > 0`) — the inverse
of the `pendingCount` the component already derives. It's a frontend-only concern: plain
session-local `$state` (`extractedOnly`), applied inside the existing `visible` derived
alongside the search filter and before sort, exactly mirroring how `search` and `sort`
work. No URL param, no localStorage, no backend change.

The count line was generalised: `countLabel` now shows "X of Y" whenever the visible set
is narrowed by **search OR** the extracted-only filter (a new `filtered` derived), and just
"Y" when nothing is filtered — previously it only reacted to a search query. The empty
state distinguishes three cases: no books at all, no search match, and (filter on) "No
extracted books yet." The filter state is exposed on the contract as
`data-verify-extracted-only`.

**Styling.** A custom `appearance:none` checkbox — hairline `--line-strong` square,
filling to `--clay` with a white tick when checked — with a mono uppercase "Extracted only"
label reusing the global `.label` style, so it sits flush beside the Sort control. The
input carries an `aria-label` (not just a wrapping `<label>`): the a11y verifier only
recognises `label[for]`/`aria-label`, so the wrapper alone would have failed the verdict.

**Verified.** `make check` clean (ruff + ty + svelte-check 0/0); `make test` green (154
backend, 91 frontend); `make verify` green. Added three additive fixtures to
`books-library.verify.ts` (`extracted-only-mixed`, `extracted-only-on`,
`extracted-only-empty` probe) with matching invariants — leaving the existing entries and
the `expectFail` sentinel untouched. Screenshotted on/off at 1280×800 and 390×844 via the
verify isolation route.

## 2026-06-05 — Favicon + per-page document titles (MY-33)

**Context.** The shell had a placeholder frying-pan emoji favicon and no `<title>` at all — every tab
read blank, and there was no brand mark in the tab strip.

**Favicon.** Replaced `static/favicon.svg` with a hand-authored **bookmark/ribbon glyph** (rounded-top,
notched-bottom silhouette) in brand clay `#d97757`. It's **dark-mode aware** via an inline
`@media (prefers-color-scheme: dark)`: on a dark tab the mark lifts to the dark-clay `#df8460` and gains
an ivory `#faf9f5` ground so it stays legible against a slate tab strip (the same clay-on-dark treatment
DESIGN §3.1 prescribes). Verified the deployed SVG flips correctly by reading computed fills under each
emulated colour-scheme. A 64×64 `favicon.png` (rasterised from the same path) is referenced as a legacy
fallback; `app.html` wires both with `type` hints plus an `apple-touch-icon`.

**Titles.** Pattern is **brand-first with a middot** — `Cookmarks · {Section}`, bare `Cookmarks` on
home. A base `<title>Cookmarks</title>` in `app.html` guarantees a title pre-hydration; each route then
sets its own via `<svelte:head>`. The pattern lives in one place — `pageTitle(section?)` in
`$lib/title.ts`. Detail routes derive the title reactively from the loaded entity (`$derived`), falling
back to bare `Cookmarks` while loading; book titles reuse `cleanTitle` so the tab matches the displayed
(subtitle-stripped) name.

**Verified.** `make check` (ruff + ty + svelte-check, 0/0), `make verify` (91), `make test`
(154 backend + 91 frontend) all green. Live on a seeded DB, every route's `document.title` confirmed via
Playwright `browser_evaluate` — including `/recipes/{id}` → `Cookmarks · Sumiso`, `/books/{id}` →
`Cookmarks · A Modern Way to Cook` (subtitle stripped), and `/lists/{id}` → `Cookmarks · Favourites`.

## 2026-06-05 — List & book cards clickable across their whole surface (MY-7)

**Context.** On `/lists` and `/books`, only the title (and, on books, the cover plate) navigated; the
rest of each card was dead space. MY-7 asks for the whole card surface to be one click target, while
keeping genuine action controls (Rename / Delete) independently clickable.

**Decision — the stretched-link pattern, not a wrapping `<a>`.** Nesting the footer buttons inside a
card-spanning anchor would be invalid HTML and would trip the load-bearing a11y verifier. Instead the
card root is `position: relative` and the single primary nav `<a>` carries a `::after { inset: 0 }`
overlay that covers the whole card. `ListCard`'s footer (`.rename-btn` / `.delete-btn`) gets
`position: relative; z-index: 1` so it sits above the overlay and stays clickable without navigating.
`BookCard` had two `<a>`s to the same place (cover plate + title); these collapse into one `.card-link`
whose stretched overlay spans the plate *and* the meta block, and the title heading drops its inner
`<a>` (now plain text under the overlay). The default Favourites card and the rename/confirm modes
render no nav link, so they're untouched. Recipes (rendered as `RecipeRow`) are deliberately out of
scope — a row has two distinct destinations (recipe + source book) plus a remove button, so
whole-surface click is ambiguous by design.

**Hover affordance.** Hovering anywhere on a card now applies to the whole card: border →
`var(--clay)`, title/name → `var(--clay-deep)`. No shadow / no lift, per DESIGN's near-flat
treatment. The hover moved from `.link:hover .name` / `.plate-link:hover .plate` to `.card:hover …`.

**Verified.** `make verify` (53 matrix fixtures), `make check` (ruff + ty + svelte-check, 0/0), and
`make test` (154 backend + 91 frontend) all green. New invariants assert each card exposes exactly one
stretched nav link to its detail page and that no `<button>` is nested inside an `<a>`; existing
selectors (`.card`, `.rename-btn`, `.delete-btn`, `.title`, `.count-badge`) and the expectFail
sentinels are preserved. Live (Playwright on the verify isolation routes): clicking the card body
navigates (`/lists/wk`, `/books/a1`) — Playwright reports the stretched overlay intercepts pointer
events over the title/meta area — while clicking Delete does not navigate, it enters the confirm step.
Desktop/mobile/hover screenshots under `docs/screenshots/my-7/`.

## 2026-06-05 — Extract a book: trigger + real Redis-backed background execution (MY-9)

The vertical slice that turns extraction into something you start from the running app. Until now
extraction only ran *inline* via a direct function call; the Celery wrappers existed but nothing
dispatched them, the broker was `memory://`, there was no trigger and no UI control, and a crash left
a run wedged in `RUNNING`. This wires the trigger end to end and folds in the deferred broker ticket
(MY-8). **Scope call:** the live "watch it run" view is *out of scope* here — deferred to MY-11, which
builds on the run schema this slice lands. So the trigger is **fire-and-forget**.

**Background execution (the MY-8 fold-in).** Broker + result backend now default to Redis
(`redis://localhost:6379/{0,1}`, overridable via env) — construction still doesn't connect, so imports
stay cheap. `celery_app` gained `include=["app.tasks.extraction"]` so a worker registers the tasks.
`Procfile` grew two processes — `redis: redis-server --save '' --appendonly no` and `worker: … celery
… --concurrency=1` (each task already fans chapters across 16 threads, and SQLite is single-writer, so
one task at a time). Dev needs a local `redis-server` (apt); prod is a later single s6/supervisord
container (not this slice). This is shared infra — future backfills/sync reuse it; extraction is its
first consumer.

**Trigger (UI + API).** `POST /api/books/{id}/extract` (`app/api/extraction.py`, mirrors v1
`POST /book/<id>/extract/`) creates a `QUEUED` `ExtractionRun` up front — so a trigger is recorded
even before a worker picks it up — then dispatches through the single `enqueue_extract_recipes` seam
and returns `202` with the run. Plain Extract: provider comes from `Config`, method/model are chosen
by the graph. On the book page the `ExtractButton` (clay accent — extraction is a "key action" per
DESIGN) labels **Extract recipes** / **Re-extract** by recipe count and runs idle → posting → "Queued
✓" → idle; a rejected dispatch surfaces an honest **error** state, never a false queued. It's a pure,
network-free component (handler injected, à la `FavouriteToggle`); the page wires `onExtract` to
`triggerExtraction`. Re-extraction reconciles recipes by normalised name (existing task contract), so
favourites/list membership survive a re-run.

**Correctness.** The task wrapper now marks a crashed run `FAILED` — error appended, `completed_at`
stamped — then re-raises so Celery captures the traceback. (No double-trigger guard and no incremental
progress commits this slice — deliberately deferred; there's no live view to feed yet.)

**Harness.** New `ExtractionRunRead` (a complete, honest run record — status, strategy, progress as a
`chapters_processed` count, cost/tokens, errors, timestamps; reused by MY-11) pinned both sides via
`contract/extractionrun.example.json` (`cost_usd` a string, datetimes ISO `Z` — the example was dumped
from the model so it round-trips exactly). New verify unit `extract-button` (idle/relabel/queued/error
fixtures + a reject probe + the `expectFail` sentinel).

**Verified.** `make check` (ruff + ty + svelte-check, 0/0); 160 backend tests — new
`test_extraction_api` (queued run + 202 + dispatched once + 404) and a FAILED-on-error task test, plus
the contract pin both sides; 97 frontend tests incl. the verify matrix's six new `extract-button`
fixtures. Live end-to-end against a copy of the prod DB with the real **Gemini** provider: triggering
*The Cook You Want to Be* from the running app dispatched through Redis to a real Celery worker, which
extracted, saved and embedded **110 recipes** across 10 chapters in ~34s for **$0.044** (139k in / 75k
out tokens) and finished `done` — the run row carries the cost/token totals. (A book whose recipes come
back image-less on the file path instead pauses at REVIEW — that resume UI is MY-10; the FAILED path is
covered by the task test.) Caught and fixed a real gap on the way: the Redis client wasn't a dependency
(`celery[redis]`).

## 2026-06-07 — Resolve the human-in-the-loop image question (MY-10)

**Goal.** Make the one human-in-the-loop decision actionable from the app: when a file-method run finds
zero images it pauses at the graph's `await_human` interrupt (status `REVIEW`) and asks *"Zero images
found. Does this cookbook have photos?"* — the operator answers and the run resumes to completion. The
backend pause/checkpoint/resume machinery was already ported from v1 (`await_human_decision`, the SQLite
checkpointer, `resume_extraction`); what was missing was the API + UI to act on it.

**Scope.** The live "watch it run" view is descoped (still MY-11), so MY-10 doesn't build a run-detail
surface — it hangs the question off the **book page** instead. Fire-and-forget throughout, matching MY-9:
no polling, no live status.

**Single source of truth.** The question text, the choices offered, and the answers accepted now live in
one place — `app/services/extraction/review.py` (`REVIEW_QUESTION`, `REVIEW_CHOICES`,
`VALID_HUMAN_RESPONSES`) — shared by the graph (raises the interrupt), `resume_extraction` (validates the
answer), and the new `ReviewQuestion` schema (surfaces it). The graph and the UI can never drift on what
is asked, and `test_review_question_current_matches_contract` pins the *actual* graph question to the
contract example.

**Surface.** `GET /api/books/{id}/extraction` returns the book's latest run (`ExtractionRunRead | null`);
`ExtractionRunRead` gains `pending_question`, populated only while the run is `REVIEW`. On load the book
page fetches it; if paused, `BookDetail` renders the new `ReviewPrompt` unit (the question + one button
per choice). **Answer.** `POST /api/books/{id}/extract/{run_id}/resume` validates the run belongs to the
book (404), the answer is a graph choice (422) and the run is actually awaiting review (409), then
dispatches `enqueue_resume_extraction` to the worker and returns `202` — the prompt clears optimistically.

**Harness.** `ReviewQuestion` pinned both sides via `contract/reviewquestion.example.json`;
`extractionrun.example.json` gains `pending_question: null`. New verify unit `review-prompt` covers the
pending question, a successful answer, the **no-pending-question** and **already-answered** (submitted)
states, a reject probe (failed resume → error, never a false submitted), an odd-choice a11y probe, and
the `expectFail` sentinel.

**Verified.** `make check` clean (ruff + ty + svelte-check, 0/0); 171 backend tests (new latest-run +
resume API tests covering 202/404/409/422 and a cross-book run, plus the two contract pins); the verify
matrix and 104 frontend tests green incl. the six new `review-prompt` fixtures. Per the visual-verify
rule, no screenshots this round (not requested). Snag fixed on the way: naming a `$derived` variable
`state` (alongside the `$state` rune) made svelte-check collapse the runes to `any` — renamed to
`displayState`.

## 2026-06-07 — Admin page + Config settings, first tab (MY-12)

The first slice of the config/operations surface: an **`/admin` page with a tab strip**, landing
**Settings** as the first tab over the `Config` singleton. The shell is built so the MY-11 extraction
reports drop in later as a second tab with no rework. A fifth **Admin** link joins the top nav (clay
active-underline; the `<480px` rule tightened so five items + wordmark + toggle stay single-row).

**Scope, deliberately lean.** Settings covers **AI provider**, a **write-only API key**, and the
**extraction rate limit**. Per-role `model_overrides` are deferred (the column stays, no UI yet); so are
a live "test the key" provider check and any auth gate (this stays open, single-user, like the rest of
the app). No migration — every column already exists on `Config`.

**Backend.** `GET`/`PATCH /api/config` (`app/api/config.py`) over the singleton via the existing
`get_config` seam. `ConfigRead` (`schemas/config.py`) exposes `ai_provider`, a derived **`api_key_set`**
boolean (the key itself is **never serialised**), `extraction_rate_limit_per_minute`, and a `providers`
catalogue (`provider_catalogue()` on the AI registry → `{name, requires_api_key}`) so the form can build
its dropdown and decide whether to show the key field. `ConfigUpdate` is an all-optional PATCH applied
with `model_dump(exclude_unset=True)`: an omitted field is untouched, and for `api_key` an empty string
or null **clears** the stored key while a non-empty string **sets/rotates** it. `GET` doesn't commit, so
a first read materialises defaults without a write.

**Frontend.** A presentational, network-free `ConfigSettings.svelte` (the verifiable unit): provider
`<select>`, a key field with a **set / not-set** state (`•••• set` + Replace/Clear, hidden for keyless
providers like Stub), and a numeric rate limit; dirty-tracking gates Save, which drives idle → saving →
saved (or → error on a rejected PATCH), mirroring `ExtractButton`. The route (`routes/admin/+page.svelte`)
fetches via a typed+Zod client (`lib/api/config.ts`), maps the snake_case wire shape to the component's
props, and re-seeds the form from the PATCH response on save. A small `AdminTabs.svelte` carries the
(currently single-tab) strip.

**Harness.** `ConfigRead` pinned both sides via `contract/config.example.json`. New verify unit
`config-settings` — fixtures for unset / key-set / keyless-provider / edit-and-save, probes for a
rejected save, a pending key-clear and an absurd rate limit, plus the `expectFail` truthfulness
sentinel. (Gotcha fixed: a local variable named `state` made svelte2tsx read `$state` as a legacy
store-subscription — renamed to `saveState`; editable fields seed from the config via an effect rather
than `$state(prop)`, which also clears the `state_referenced_locally` warnings.)

**Verified.** `make check` (ruff + ty + svelte-check, 0/0); `make test` — 171 backend tests (new
`test_config`: defaults + catalogue, set/rotate/clear/omit the key, key never echoed, rate-limit < 1 →
422) and 103 frontend tests incl. the verify matrix's eight new `config-settings` fixtures and the
config contract pin both sides.

## 2026-06-07 — Book-level keywords (AI-generated, shared vocabulary)

Books gain keywords — book-level tags (cuisine/theme/style) that say what a whole cookbook is about,
shown on the library cards and the book detail page. **Decisions** (all from first principles): tags are
**AI-generated per book**, not imported from Calibre; they draw from the **same shared `Keyword`
vocabulary** as recipes (one `chicken`, one row, counts unify), so this is a new association, not a new
vocabulary; UI surfaces are the **library cards** and the **detail masthead** (no filtering UI this
slice).

**Data.** New `book_keywords` association (book_id, keyword_id PK; `keyword_id` indexed like
`recipe_keywords`, both FKs `ON DELETE CASCADE`) with `Book.keywords` ↔ `Keyword.books`. The migration
`a1b2c3d4e5f6` also **merges the two divergent heads** the repo had drifted into (the keyword-index
branch and the config-overrides branch) back to one. Unlinking a book leaves the shared keyword in
place.

**Generation.** New `ModelRole.BOOK_KEYWORDS` (mapped on Gemini/OpenRouter/Stub) + `BOOK_KEYWORDS_PROMPT`
and `AIProvider.generate_book_keywords(digest)` (parses a JSON string array, cleaned/deduped/capped at
`MAX_BOOK_KEYWORDS=10`). `app/services/book_keywords.py` builds the digest from the book's metadata plus
a sample of its recipe names and the most-common recipe tags — enough signal to infer cuisine/theme even
when the blurb is thin — then assigns via a shared `get_or_create_keyword` (extracted to
`app/services/keywords.py`, now used by both recipe and book paths). Population: best-effort at the end
of a successful extraction (a no-op without a provider, never fails the run, like embeddings) +
`scripts/backfill_book_keywords.py` for existing books (`--all` to regenerate). The **Stub** returns
deterministic, per-book offline tags so tests/dev work without a network.

**Read surfaces.** `keywords` added to `BookSummary` and `BookDetail` (endpoints eager-load with
`selectinload` to avoid an N+1); `BookCard` shows up to three chips (desktop grid only — hidden on the
mobile row list), `BookDetail` shows the full set under the byline. A real correctness catch:
`/api/keywords` (the recipe filter chips) was an **outer** join over `keywords`, so book-only tags would
have leaked in as recipe filters — switched to an **inner** join so it stays recipe-scoped. The home
`keywords` stat counts the whole shared vocabulary (recipe + book).

**Harness.** `contract/books.example.json` gained `keywords` (pins `BookSummary` both sides). Verify
units extended: `book-detail` has a `data-verify-keywords` count + a chip invariant (and the long-title
probe now stresses many book tags); `books-library` asserts each card renders up to three chips, with a
mixed fixture (one book over the cap, one with none).

**Verified.** `make check` (ruff + ty + svelte-check, 0/0); 164 backend tests (new `test_book_keywords`:
read surfaces + the generation service reusing the shared vocabulary + the no-provider no-op; updated
the books/home/keyword shape tests for the new field and the inner-join scoping); 97 frontend tests incl.
the verify matrix. Migration applies cleanly to a single head on a fresh DB. Not yet run against the
real Gemini provider on prod data — the Stub path is the verified one this slice.

## 2026-06-07 — Admin Tasks tab: on-demand book-keyword generation

The operational counterpart to the book-keywords slice: a **Tasks** tab on `/admin` (the second tab after
Settings, built on the MY-12 admin shell) with an on-demand **Generate book keywords** trigger. Extraction
already tags new books; this fills in the rest — or re-tags everything — without re-extracting.

**Backend.** A library-wide sweep, `app/tasks/book_keywords.py::backfill_book_keywords(regenerate)`, wraps
the per-book `generate_book_keywords` over every extracted book missing keywords (or, with `regenerate`,
every extracted book). One code path now serves all three callers — the CLI script (rewritten to call it),
the Celery worker (`backfill_book_keywords_task`, registered via the celery `include`), and the new
endpoint. `POST /api/tasks/book-keywords` (`app/api/tasks.py`) counts the eligible books, dispatches
through the `enqueue_backfill_book_keywords` seam, and returns `202` + `TaskRunAck {task, status, queued}`
— fire-and-forget, mirroring the extraction trigger (no live progress; MY-11 territory).

**Frontend.** A presentational, network-free `TasksPanel.svelte` (the verifiable unit): a task card with a
**Regenerate all** toggle and a Run button that drives idle → running → queued (showing how many books were
queued, or a calm "everything's up to date" when zero) → idle, or → error on a rejected dispatch — the
ExtractButton state-machine shape. The admin route adds the Tasks tab and wires `onRun` to a typed+Zod
client (`lib/api/tasks.ts`); the tab renders independently of the Settings config load.

**Harness.** `TaskRunAck` pinned both sides via `contract/taskrun.example.json`. New verify unit
`tasks-panel` — idle / run / run-nothing / regenerate-passed fixtures (the last proves the flag reaches the
handler), a reject probe and an absurd-count probe, plus the `expectFail` sentinel. (Re-hit the documented
`state`-named-variable gotcha — a local `state` collapses the `$state` runes to `any` under svelte-check —
renamed to `runState`.)

**Verified.** `make check` (ruff + ty + svelte-check, 0/0); 192 backend tests (new `test_tasks_api`:
trigger eligible-count for default vs regenerate + dispatched once, and the sweep against a patched
`SessionLocal` — tags untagged books, no-op without a provider — plus the contract pin both sides); 116
frontend tests incl. the verify matrix's seven new `tasks-panel` fixtures. Fire-and-forget dispatch stubbed
in tests (new autouse `tasks_dispatched` fixture); not run against a live worker/Gemini this slice.

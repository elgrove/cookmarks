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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Cookmarks v2 — a rebuild of the Django/HTMX v1 onto a **typed-Python FastAPI backend + Svelte SPA**. v1's proven Python service/extraction logic (LangGraph extraction, AI providers, sqlite-vec embeddings, Calibre parsing) is ported in later milestones; this scaffold establishes the app skeleton and, above all, the **agent-verifiable harness**.

**The v1 codebase is the reference for porting.** It lives at `/home/aaron/dev/cookmarks` (branch `main`). V1 is to be used as a guide, in V2 all core concepts and decisions can be re-thought from first principles, with the exception of recipe extraction, which is proven to work as-is.

## UI design language

**`DESIGN.md` is the canonical spec for how the v2 UI looks and feels** — read it before building or changing any UI. In short: a warm, text-first **editorial-archive** aesthetic — warm ivory ground + clay accent, a Schibsted Grotesk / Source Serif 4 / IBM Plex Mono type system, numbered index layouts, and a deliberately-designed **no-image** state (most recipes have none). Palette and type take their cue from Anthropic's brand identity (by Geist). `DESIGN.md` is self-contained — tokens, components, and screens — and is the only document needed to build the UI.

## Repository layout & worktree workflow

This checkout — `~/dev/cookmarks-v2`, branch `v2` — is the **v2 trunk**: the integration branch every piece of v2 work merges back into. The v1 reference at `~/dev/cookmarks` (branch `main`) **owns the shared git store** (`~/dev/cookmarks/.git`); each worktree, including this one, is just a pointer into it, so don't move or delete the v1 checkout.

Do all work in a **sub-worktree branched off `v2`** — never edit the trunk directly — so `v2` stays clean and merges stay trivial. Sub-worktrees live under `.claude/worktrees/<branch>/` (gitignored):

```bash
cd ~/dev/cookmarks-v2
git worktree add -b <branch> .claude/worktrees/<branch> v2   # branch off the trunk
# ... work and commit inside the sub-worktree ...
cd ~/dev/cookmarks-v2 && git merge <branch>                  # land back on the trunk
git worktree remove .claude/worktrees/<branch>               # clean up
```

This overrides the global rule about basing worktrees on `origin/main`: for v2 work the base is the local `v2` trunk.

The defining principle (inspired by Anthropic's "Verifiable React" workshop, re-derived for this stack): **verification is an architectural concern, not a test afterthought.** Every UI unit exposes a machine-readable `data-verify-*` DOM contract, mounts in isolation at `/verify/:unit/:fixture`, and is checked through one verdict taxonomy via a single code path (`runFixture`) shared by three consumers — the **agent** (live browser), the **dashboard** (human), and **CI** (headless matrix).

## Stack

- **Backend** (`backend/`): FastAPI · SQLAlchemy 2.0 + Alembic · Celery · SQLite · `uv` · Python 3.11. Type-checked with **ty**, linted/formatted with **ruff**, tested with **pytest**.
- **Frontend** (`frontend/`): SvelteKit (`adapter-static`, SPA mode) · Vite · TypeScript · Zod. Tested with **vitest** (jsdom). Type-checked with **svelte-check**.
- **Serving**: dev runs two processes — Vite (`:9789`, HMR) proxies `/api` → uvicorn (`:9788`). Prod builds the SPA to `frontend/build/`, which FastAPI serves with an SPA catch-all fallback (`app/static.py`) — single origin, no CORS.

## Commands

Run from the repo root unless noted.

- `make install` — `uv sync` (backend) + `npm install` (frontend).
- `make migrate` — apply Alembic migrations (`uv run python -m alembic upgrade head`). The `alembic` console script isn't installed; use the `python -m alembic` module form for revisions too.
- `make dev` — both dev servers via honcho (`uvx honcho start`, reads `Procfile`).
- `make verify` — **the headless verification matrix** (`vitest run`): every unit × fixture, prints verdicts. Fast inner loop.
- `make check` — backend `ruff check` + `ty check`; frontend `svelte-check`.
- `make test` — backend `pytest`; frontend `vitest`.
- `make build` — build the SPA into `frontend/build/`.
- Single backend test: `cd backend && uv run pytest tests/test_health.py::test_health`.
- Single frontend test file: `cd frontend && npx vitest run src/lib/verify/harness.test.ts`.

## Data layer

SQLite (`backend/db.sqlite3` by default; `COOKMARKS_DB_PATH` overrides — see `app/config.py`). `app/db.py` loads the **sqlite-vec** extension and sets `PRAGMA foreign_keys=ON` on every connection (SQLite ignores foreign keys and `ON DELETE` otherwise).

- **Models** (`app/models/`, one module per aggregate): SQLAlchemy 2.0 declarative — `Book`, `Recipe` (+ `Keyword` and the `recipe_keywords` association), `RecipeList`/`RecipeListItem`, `ExtractionRun`, and a singleton `Config`. All inherit `UUIDAuditBase` (`base.py`): UUID PK + `created_at`/`updated_at`. Choice fields are `StrEnum`s (`enums.py`), stored by value. The schema mirrors v1's domain, re-thought from first principles — **except `ExtractionRun`**, which tracks v1's `ExtractionReport` faithfully (method, image flags, chapter progress) since extraction is carried over as-is.
- **Recipe identity** is stable across re-extraction: the extraction task reconciles by matching on the normalised name within a book (update in place, not wipe-and-recreate), so favourites and list membership survive a re-run. This is a contract on the extraction task, not enforced by schema.
- **Migrations** (`backend/alembic/`, excluded from lint/typecheck): autogenerate with `uv run python -m alembic revision --autogenerate -m "..."` from `backend/`, apply with `make migrate`.
- **Embeddings**: a `recipe_embeddings` **vec0** virtual table, separate from the ORM (not in Alembic), keyed by the hyphenated UUID string (`str(recipe.id)`) — note `recipes.id` is stored *un-hyphenated*, so a raw join matches nothing; `app/services/vector_store.py` (`VectorStore`) is the only place that bridges the two formats. It wraps the session connection (sqlite-vec already loaded by `app/db.py`), self-creates the table `IF NOT EXISTS` (so a fresh/test DB reads as empty rather than erroring), and exposes `get_embedding` / `search` / `search_excluding` / `upsert`. First consumer is **similar recipes** (`GET /api/recipes/{id}/similar`); the search milestone adds query-embedding *generation* (the AI call) on top of the same store.
- **Seeding dev data**: `cd backend && uv run python -m scripts.import_v1_data` copies real data (books, recipes, keywords, lists, runs, config, embeddings) from the v1 production SQLite into the v2 DB, preserving UUIDs. Re-runnable (clears then repopulates); `--source PATH`, `--no-embeddings`.

## The agent feedback loop (read this before changing UI)

This harness exists so you can **drive the app and correct yourself**. Three ways to observe, same `runFixture` code path underneath:

1. **Headless (fastest):** run `make verify`. Every fixture that isn't an `expectFail` sentinel must be `PASS` (probes included); the matrix asserts it. Use this as your inner loop after any harness/unit change.
2. **Live (self-correction via Playwright MCP):** `make dev`, then navigate the browser to:
   - `http://localhost:9789/verify` — dashboard; click "Run all", read the verdict grid.
   - `http://localhost:9789/verify/<unit>/<fixture>?chrome=0` — one unit mounted in isolation, chrome stripped for clean screenshots. The mounted instance **is** the verified one (`act` applied to it), so the screenshot can never disagree with the verdict.
   - Read structured results without evaluating JS by scraping `#verify-result-json` (the latest `current()`/`runAll()` payload), or call `window.__verify.runAll()` / `window.__verify.manifest()`.
3. **Human:** open `/verify` to eyeball the grid.

`window.__verify` API: `manifest()`, `current()`, `runAll()`, `version`.

## Adding a verifiable unit

1. Build a Svelte component that emits a `data-verify-*` contract on a self-identifying root element (`data-verify-unit="<id>"` plus whatever state attributes the invariants need).
2. Add a `*.verify.ts` anywhere under `src/` that **default-exports a `VerifiableUnit`** (`src/lib/verify/types.ts`). It is auto-discovered via `import.meta.glob` in `src/lib/verify/registry.ts` — no manual registration.
3. Declare `fixtures` (named prop sets; mark adversarial ones `probe: true`), `invariants` (predicates over the DOM contract), and an optional Zod `propsSchema`. Every unit must ship **≥1 probe** (the matrix enforces it). `probe` and the verdict are **orthogonal**: a probe is an adversarial *input* that must still `PASS`. The only fixture allowed (and required) to `FAIL` is the **truthfulness sentinel** marked `expectFail: true`.
4. Verifiers (`src/lib/verify/verifiers/`): `dom-contract`, `schema`, `invariants`, `a11y`. Add a new one by writing a file and appending it to `verifiers/index.ts` — units are untouched. The `a11y` verifier is **load-bearing** (DESIGN §8): unnamed buttons, unlabelled inputs and alt-less images `fail` the verdict, not just warn.

Verdict rules (`runner.ts`): any `fail` check → `FAIL`; mount error → `BLOCKED` (couldn't observe, distinct from a real failure); no fixtures → `SKIP`; otherwise `PASS`. Warnings never fail a verdict. The matrix enforces every non-`expectFail` fixture is `PASS` and every `expectFail` sentinel is `FAIL`. When in doubt, the harness fails rather than greenwashes.

**The backend ↔ frontend wire contract** is pinned from both sides by the `contract/*.example.json` files (see `contract/README.md`): `backend/tests/test_contract.py` asserts each Pydantic model serialises to the example, and `frontend/src/lib/api/contract.test.ts` asserts the Zod schemas accept it. A one-sided field rename fails CI instead of only breaking at runtime.

`src/lib/components/Smoke.svelte` + `src/verify-units/_smoke.verify.ts` are a temporary self-test (a passing fixture and a deliberately-failing probe). **Delete both once the first real unit lands.**

## Conventions

- **Maintain `REBUILD_LOG.md`** — the running journal of the rebuild. Append an entry (context, decisions, outcome) whenever a meaningful chunk of work lands. CLAUDE.md is the current-state snapshot; the log is the history.
- Backend: ruff (line length 100), strict `ty`, British spelling. Imports at top of module only. Alembic migrations live in `backend/alembic/` (excluded from lint/typecheck).
- Frontend: TypeScript strict; harness tests must stay free of SvelteKit (`$app/*`) imports so they run in plain vitest.
- Celery: `app/tasks/celery_app.py` holds the app; `app/tasks/extraction.py` is the first real worker — `extract_recipes_from_book` / `resume_extraction` tasks (callable inline; the LangGraph pipeline lives in `app/services/extraction/`). The broker is still `memory://`; a real broker (likely Redis) is wired when extraction runs in the background rather than inline.

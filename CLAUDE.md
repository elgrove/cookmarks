# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Cookmarks v2 — a rebuild of the Django/HTMX v1 onto a **typed-Python FastAPI backend + Svelte SPA**. v1's proven Python service/extraction logic (LangGraph extraction, AI providers, sqlite-vec embeddings, Calibre parsing) is ported in later milestones; this scaffold establishes the app skeleton and, above all, the **agent-verifiable harness**.

**The v1 codebase is the reference for porting.** It lives at `/home/aaron/dev/cookmarks` (branch `main`) — read its `CLAUDE.md` for v1's architecture, and lift the framework-agnostic service code from `core/services/` (extraction graph, `ai.py`, `embeddings.py`, Calibre/EPUB) when wiring up each v2 feature. The Django ORM models, Django-Q tasks, and HTMX views are *not* ported as-is — they map to SQLAlchemy models, Celery tasks, and FastAPI routes respectively.

The defining principle (inspired by Anthropic's "Verifiable React" workshop, re-derived for this stack): **verification is an architectural concern, not a test afterthought.** Every UI unit exposes a machine-readable `data-verify-*` DOM contract, mounts in isolation at `/verify/:unit/:fixture`, and is checked through one verdict taxonomy via a single code path (`runFixture`) shared by three consumers — the **agent** (live browser), the **dashboard** (human), and **CI** (headless matrix).

## Stack

- **Backend** (`backend/`): FastAPI · SQLAlchemy 2.0 + Alembic · Celery · SQLite · `uv` · Python 3.11. Type-checked with **ty**, linted/formatted with **ruff**, tested with **pytest**.
- **Frontend** (`frontend/`): SvelteKit (`adapter-static`, SPA mode) · Vite · TypeScript · Zod. Tested with **vitest** (jsdom). Type-checked with **svelte-check**.
- **Serving**: dev runs two processes — Vite (`:9789`, HMR) proxies `/api` → uvicorn (`:9788`). Prod builds the SPA to `frontend/build/`, which FastAPI serves with an SPA catch-all fallback (`app/static.py`) — single origin, no CORS.

## Commands

Run from the repo root unless noted.

- `make install` — `uv sync` (backend) + `npm install` (frontend).
- `make dev` — both dev servers via honcho (`uvx honcho start`, reads `Procfile`).
- `make verify` — **the headless verification matrix** (`vitest run`): every unit × fixture, prints verdicts. Fast inner loop.
- `make check` — backend `ruff check` + `ty check`; frontend `svelte-check`.
- `make test` — backend `pytest`; frontend `vitest`.
- `make build` — build the SPA into `frontend/build/`.
- Single backend test: `cd backend && uv run pytest tests/test_health.py::test_health`.
- Single frontend test file: `cd frontend && npx vitest run src/lib/verify/harness.test.ts`.

## The agent feedback loop (read this before changing UI)

This harness exists so you can **drive the app and correct yourself**. Three ways to observe, same `runFixture` code path underneath:

1. **Headless (fastest):** run `make verify`. Non-probe fixtures must be `PASS`; the matrix asserts it. Use this as your inner loop after any harness/unit change.
2. **Live (self-correction via Playwright MCP):** `make dev`, then navigate the browser to:
   - `http://localhost:9789/verify` — dashboard; click "Run all", read the verdict grid.
   - `http://localhost:9789/verify/<unit>/<fixture>?chrome=0` — one unit mounted in isolation, chrome stripped for clean screenshots.
   - Read structured results without evaluating JS by scraping `#verify-result-json` (the latest `current()`/`runAll()` payload), or call `window.__verify.runAll()` / `window.__verify.manifest()`.
3. **Human:** open `/verify` to eyeball the grid.

`window.__verify` API: `manifest()`, `current()`, `runAll()`, `version`.

## Adding a verifiable unit

1. Build a Svelte component that emits a `data-verify-*` contract on a self-identifying root element (`data-verify-unit="<id>"` plus whatever state attributes the invariants need).
2. Add a `*.verify.ts` anywhere under `src/` that **default-exports a `VerifiableUnit`** (`src/lib/verify/types.ts`). It is auto-discovered via `import.meta.glob` in `src/lib/verify/registry.ts` — no manual registration.
3. Declare `fixtures` (named prop sets; mark adversarial ones `probe: true`), `invariants` (predicates over the DOM contract), and an optional Zod `propsSchema`. Every unit must ship **≥1 probe** (the matrix enforces it).
4. Verifiers (`src/lib/verify/verifiers/`): `dom-contract`, `schema`, `invariants`, `a11y`. Add a new one by writing a file and appending it to `verifiers/index.ts` — units are untouched.

Verdict rules (`runner.ts`): any `fail` check → `FAIL`; mount error → `BLOCKED` (couldn't observe, distinct from a real failure); no fixtures → `SKIP`; otherwise `PASS`. Warnings never fail a verdict. When in doubt, the harness fails rather than greenwashes.

`src/lib/components/Smoke.svelte` + `src/verify-units/_smoke.verify.ts` are a temporary self-test (a passing fixture and a deliberately-failing probe). **Delete both once the first real unit lands.**

## Conventions

- Backend: ruff (line length 100), strict `ty`, British spelling. Imports at top of module only. Alembic migrations live in `backend/alembic/` (excluded from lint/typecheck).
- Frontend: TypeScript strict; harness tests must stay free of SvelteKit (`$app/*`) imports so they run in plain vitest.
- Celery: `app/tasks/celery_app.py` is a skeleton with a `ping` task; the broker (likely Redis) is wired when the real worker is ported.

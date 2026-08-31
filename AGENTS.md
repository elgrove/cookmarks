# AGENTS.md

This file provides guidance to coding agents when working with this repository.

## What this is

Cookmarks — a **typed-Python FastAPI backend + Svelte SPA** for extracting, browsing and searching recipes out of a Calibre cookbook library. It replaced a Django/HTMX predecessor (the "v1" rebuilt from first principles, except recipe extraction, which was ported as-is because it was proven); v1 is history now, kept on branch `dev` if an old implementation ever needs consulting.

The app is **live in production** — see the Docker section below.

## UI design language

**`DESIGN.md` is the canonical spec for how the UI looks and feels** — read it before building or changing any UI. In short: a warm, text-first **editorial-archive** aesthetic — warm ivory ground + clay accent, a Schibsted Grotesk / Source Serif 4 / IBM Plex Mono type system, numbered index layouts, and a deliberately-designed **no-image** state (most recipes have none). Palette and type take their cue from Anthropic's brand identity (by Geist). `DESIGN.md` is self-contained — tokens, components, and screens — and is the only document needed to build the UI.

## Repository layout & worktree workflow

This checkout — `~/dev/cookmarks`, branch `main` — is the **trunk**: the integration branch every piece of work merges back into, and the build context prod deploys from.

Do all work in a **sub-worktree branched off `main`** — never edit the trunk directly — so `main` stays clean and merges stay trivial. Sub-worktrees live under `.claude/worktrees/<branch>/` (gitignored):

```bash
cd ~/dev/cookmarks
git worktree add -b <branch> .claude/worktrees/<branch> main   # branch off the trunk
# ... work and commit inside the sub-worktree ...
# Always squash merge — every PR / branch lands as exactly one commit on main:
gh pr merge <pr-number> --squash --delete-branch              # via PR (standard)
# or if landing locally without a PR:
git checkout main && git merge --squash <branch> && git commit -m "<msg>"
git worktree remove .claude/worktrees/<branch>                 # clean up
```

**Squash merge is mandatory for all GitHub PRs and landed work.** Every PR must affect exactly one commit on `main`, keeping git history clean, strictly linear, and easy to bisect or revert. Never use standard merge commits or rebase merges for PRs.


This overrides the global rule about worktree location (`~/home/.worktrees/…`): here they live inside the checkout, based on the local `main`.

The one sanctioned exception to "never edit the trunk" is the **`work-on-main` skill** — interactive pair-programming on the live checkout, invoked explicitly by the user.

The defining principle (inspired by Anthropic's "Verifiable React" workshop, re-derived for this stack): **verification is an architectural concern, not a test afterthought.** Every UI unit exposes a machine-readable `data-verify-*` DOM contract, mounts in isolation at `/verify/:unit/:fixture`, and is checked through one verdict taxonomy via a single code path (`runFixture`) shared by three consumers — the **agent** (live browser), the **dashboard** (human), and **CI** (headless matrix).

## Stack

- **Backend** (`backend/`): FastAPI · SQLAlchemy 2.0 + Alembic · Celery · SQLite · `uv` · Python 3.11. Type-checked with **ty**, linted/formatted with **ruff**, tested with **pytest**.
- **Frontend** (`frontend/`): SvelteKit (`adapter-static`, SPA mode) · Vite · TypeScript · Zod. Tested with **vitest** (jsdom). Type-checked with **svelte-check**.
- **Serving**: dev runs two processes — Vite (`:9789`, HMR) proxies `/api` → uvicorn (`:9788`). Prod builds the SPA to `frontend/build/`, which FastAPI serves with an SPA catch-all fallback (`app/static.py`) — single origin, no CORS.
- **Port convention**: ports follow `<slot>789` (web) / `<slot>788` (api) / `<slot>787` (redis). Slot **8** = prod (`8789`), slot **9** = trunk (`9789`, plain `make dev`); slots **2–7** are ad-hoc dev servers handed out by `make dev-auto`. Each slot has its own Redis (broker db 0 / result db 1) so workers don't poach each other's tasks.

## Android

On `main`, Android SDK tools are installed but are not necessarily on `PATH`:
`/opt/android-sdk/platform-tools/adb` and `/opt/android-sdk/emulator/emulator`.

The `cookmarks` AVD is normally available and may already be running. Check with:

```sh
/opt/android-sdk/platform-tools/adb devices -l
```

Agents may build, install, control, and screenshot the Android app through ADB when visual
verification is explicitly requested.

## Commands

Run from the repo root unless noted.

- `make install` — `uv sync` (backend) + `npm install` (frontend).
- `make migrate` — apply Alembic migrations (`uv run python -m alembic upgrade head`). The `alembic` console script isn't installed; use the `python -m alembic` module form for revisions too.
- `make dev` — the four dev processes via honcho (`uvx honcho start`, reads `Procfile`): `redis`, `api` (uvicorn), `web` (vite), `worker` (Celery). Background work (extraction) runs on the worker. Needs a local Redis binary: `sudo apt install redis-server`; if the package auto-starts a systemd `redis-server` on :6379, `sudo systemctl disable --now redis-server` so honcho owns the port. Broker/backend default to `redis://localhost:6379/{0,1}` (override via `COOKMARKS_CELERY_BROKER_URL` / `_RESULT_BACKEND`). The `Procfile` reads `COOKMARKS_{WEB,API,REDIS}_PORT` (honcho passes the env through to its `/bin/sh -c` children), defaulting to the trunk ports when unset. Book ingestion shells out to Calibre, so dev also needs the **same pinned Calibre as the image** (`wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sudo sh /dev/stdin version=9.13.0`); it refuses to install until its Qt client libs are present — `sudo apt install -y --no-install-recommends libopengl0 libegl1 libglx0 libfontconfig1 libnss3 libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-xinerama0`.
- `scripts/dev_library.sh` — build (or reset) the **dev Calibre library**: a hardlink clone of the prod library pruned to the three eval books, at `~/cookmarks-dev-library`. Dev must never write to the prod library, and ingest experiments need one that can be thrown away. `calibre_id`s and paths survive the prune, so `backend/evals/eval.toml` still resolves its EPUBs. Point dev at it with `COOKMARKS_CALIBRE_LIBRARY_PATH` in `backend/.env`; re-run to reset. Consequence: a dev sync prunes a prod-seeded dev DB down to those three books.
- `make dev-auto` — same stack on the **first free slot in 2–7** (`scripts/dev.sh`), so a second dev server runs alongside the trunk without port clashes. It exports the slot's `COOKMARKS_{WEB,API,REDIS}_PORT` + `COOKMARKS_CELERY_{BROKER_URL,RESULT_BACKEND}` and launches honcho. Force a slot with `make dev-auto SLOT=5`; preview the choice without launching via `scripts/dev.sh --print`.
- `make verify` — **the headless verification matrix** (`vitest run`): every unit × fixture, prints verdicts. Fast inner loop.
- `make check` — backend `ruff check` + `ty check`; frontend `svelte-check`.
- `make test` — backend `pytest`; frontend `vitest`.
- `make build` — build the SPA into `frontend/build/`.
- Single backend test: `cd backend && uv run pytest tests/test_health.py::test_health`.
- Single frontend test file: `cd frontend && npx vitest run src/lib/verify/harness.test.ts`.

## Docker (single-container deploy)

**Production** runs this image on the home server at `http://10.0.0.11:8789`, from `~/docker/cookmarks/` (its own `docker-compose.yml` + `data/`), built locally from **whatever is checked out in `~/dev/cookmarks`** — there is no registry and no staging. Deploys go through the **deploy-prod skill** (`.claude/skills/deploy-prod/`), which builds, backs up the DB, recreates and health-checks; don't hand-roll the sequence.

`docker compose up -d --build` ships the whole stack — Redis, uvicorn (API + built SPA), and the Celery worker — in **one container** supervised by **s6-overlay**, serving on `8789`. The three-stage `Dockerfile` builds the SPA (`node:20.20.2-slim`), unpacks s6-overlay (`alpine:3.23`), and runs on `python:3.11.14-slim` (deps via `uv sync --frozen --no-dev`); base images are pinned for reproducible builds. s6 service defs live in `docker/s6/` (copied to `/etc/s6-overlay/`): oneshots `data-dirs` → `db-init` (alembic upgrade head), longruns `redis`/`api`/`worker`/`beat` (Celery beat, whose only entry is the weekly keyword dedup; its schedule file lives at `/data/celerybeat-schedule` so a rebuild does not re-fire a job it already ran). SQLite DB + embeddings + the Redis dump persist on the `./data:/data` bind-mount (`COOKMARKS_DB_PATH=/data/db.sqlite3`). The **Calibre library** is Cookmarks' own, at `~/docker/cookmarks/library`, mounted **read-write** at `/library` (covers, recipe images, book download, the reader and book sync read from it; ingestion writes to it). **Single-writer rule: only the Cookmarks worker writes to it** — no Calibre GUI, no Syncthing, nothing else. It was split out of the shared `~/books/calibre-all` everything-library by clone-and-prune, so every `calibre_id` is unchanged; the two share inodes through hardlinks, so `du` double-counts them and deleting calibre-all would reclaim only the non-food books. **Calibre 9.13.0 ships in the image** (upstream installer, pinned by the `CALIBRE_VERSION` build ARG — Debian's 6.x has rotted metadata-source plugins) for `calibredb`, `fetch-ebook-metadata`, `ebook-meta` and `ebook-convert`; it costs about 1 GB of image. Staged uploads land on the volume at `/data/ingest` (`COOKMARKS_INGEST_STAGING_PATH`). Compose ships a `healthcheck` hitting `/api/health` (`curl`, in the image). The AI key is set at runtime via the settings UI (DB `Config`), not an env secret. **Accounts:** `COOKMARKS_AUTH_MODE` is `session` (default — username + password, cookie sessions) or `none` (no login; every request runs as a single implicit user). Seed the first admin with `docker compose exec cookmarks uv run python -m scripts.create_user <name> --admin`; every account after that is created in Admin › Users. The first account ever created adopts the pre-accounts lists, so an existing deployment keeps its Favourites. **Gotcha:** a oneshot s6 `up` is an execline line, so a `with-contenv` shebang in it is ignored — `db-init/up` therefore execs the real script `docker/s6/scripts/db-init` (whose shebang pulls in the env so alembic targets the volume DB, not the in-image default).

## Data layer

SQLite (`backend/db.sqlite3` by default; `COOKMARKS_DB_PATH` overrides — see `app/config.py`). `app/db.py` loads the **sqlite-vec** extension and sets `PRAGMA foreign_keys=ON` on every connection (SQLite ignores foreign keys and `ON DELETE` otherwise).

- **Models** (`app/models/`, one module per aggregate): SQLAlchemy 2.0 declarative — `Book`, `Recipe` (+ `Keyword` and the `recipe_keywords` association), `RecipeList`/`RecipeListItem`, `TaskRun`, and a singleton `Config`. All inherit `UUIDAuditBase` (`base.py`): UUID PK + `created_at`/`updated_at`. Choice fields are `StrEnum`s (`enums.py`), stored by value. **`TaskRun`** (`task_runs` table) is the unified record of every background job — extraction is one `task_type` among `book_keywords`, `keyword_dedup`, `calibre_sync` and `book_ingest`; it carries the extraction detail (method, image flags, chapter progress) as typed columns, while the other task types report through a generic JSON `detail`. `book_id` is nullable (set on extraction runs only).
- **Recipe identity** is stable across re-extraction: the extraction task reconciles by matching on the normalised name within a book (update in place, not wipe-and-recreate), so favourites and list membership survive a re-run. This is a contract on the extraction task, not enforced by schema.
- **Migrations** (`backend/alembic/`, excluded from lint/typecheck): autogenerate with `uv run python -m alembic revision --autogenerate -m "..."` from `backend/`, apply with `make migrate`.
- **Embeddings / vector search**: a `recipe_embeddings` **vec0** virtual table, separate from the ORM (not in Alembic), keyed by the **hyphenated** UUID string (`str(recipe.id)`) — note `recipes.id` is stored *un-hyphenated*, so a raw join matches nothing. `app/services/vector_store.py` (`VectorStore`) is the single place that bridges the two formats: session-bound, self-creates the table `IF NOT EXISTS` (a fresh/test DB reads as empty), and exposes `get_embedding` / `search` / `search_excluding` / `upsert` / `embedded_ids`. On top of it, `app/services/embeddings.py` is the **generation** layer — `recipe_to_text` (name + keywords + ingredients), `embed_recipes`, query `search`, `backfill`, and a query-embedding LRU — using the embed capability on `AIProvider` (`embed`/`embed_batch`, `EmbedTask`; only **Gemini** `gemini-embedding-001`/3072-d wired, **Stub** gives deterministic offline vectors). Consumers: **similar recipes** (`GET /api/recipes/{id}/similar`, vector with shared-keyword fallback) and **semantic search** (`GET /api/recipes/semantic`); the extraction hook embeds new recipes and `scripts/backfill_embeddings.py` fills gaps. The table width is fixed at 3072, so changing embedding model would need a full re-embed (not built).
- **Seeding dev data**: `cd backend && uv run python -m scripts.import_v1_data` copies real data (books, recipes, keywords, lists, runs, config, embeddings) from the old Django SQLite into the local dev DB, preserving UUIDs. Re-runnable (clears then repopulates); `--source PATH`, `--no-embeddings`.
- **Seeding the dev login from prod**: a fresh dev DB has no accounts, so the app is unusable — seed one by copying the `aaron` row out of the prod DB (`~/docker/cookmarks/data/db.sqlite3`), which carries the password hash so the usual password works. Copy the whole prod DB the same way when dev needs real books to browse — take it with `sqlite3 <prod-db> ".backup '<tmp>'"` (prod is live, so a plain `cp` can catch a half-written WAL), drop it over `backend/db.sqlite3`, `make migrate` it up to head, then restart the stack so the API isn't holding the old file.

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

## Conventions

- Backend: ruff (line length 100), strict `ty`, British spelling. Imports at top of module only. Alembic migrations live in `backend/alembic/` (excluded from lint/typecheck).
- Frontend: TypeScript strict; harness tests must stay free of SvelteKit (`$app/*`) imports so they run in plain vitest.
- Celery: `app/tasks/celery_app.py` holds the app (broker + result backend on **Redis**, `include`s the task modules so a worker registers them); `app/tasks/extraction.py` holds the `extract_recipes_from_book` / `resume_extraction` tasks (still callable inline for the eval/tests; the LangGraph pipeline lives in `app/services/extraction/`). The trigger endpoint `POST /api/books/{id}/extract` (`app/api/extraction.py`) creates a `QUEUED` `TaskRun` (`task_type=extraction`) then dispatches via `enqueue_extract_recipes`, so the run executes on the worker off the request thread. The task wrapper marks the run `FAILED` (records the error, stamps `completed_at`) on a crash. The simpler maintenance tasks (`book_keywords`, `keyword_dedup`, `calibre_sync`, `book_ingest`) follow the same shape through a shared seam (`app/tasks/runs.py`: `create_task_run` / `start_run` / `complete_run` / `fail_run`) — their trigger endpoints (`app/api/tasks.py`) record a `QUEUED` run, then the worker drives it RUNNING → DONE (writing its metrics into `detail`) or FAILED. Every run, whatever its type, surfaces newest-first at `GET /api/task-runs?type=` (`app/api/task_runs.py`, schema `TaskRunRead`) in the admin **Task Runs** tab. Tests stub the dispatch (`dispatched` / `resume_dispatched` / `tasks_dispatched` / `dedup_dispatched` / `calibre_dispatched` / `ingest_dispatched` fixtures in `tests/conftest.py`) and never reach Redis.
- **Book ingestion** (`app/services/ingest.py`, admin-only): the Add-book page stages an upload or a download link, then a `book_ingest` run converts it to EPUB unless it is already a format the library holds as it is (**EPUB or PDF** — a fixed-layout cookbook does not survive `ebook-convert`), fetches metadata + cover, `calibredb add`s it, applies the metadata (forcing the user's title/author over the fetched OPF and adding the `Food` tag), and syncs it in. Every subprocess goes through one seam, `run_cli`, which the tests replace. Two Calibre behaviours are load-bearing and pinned by tests: **every binary writes GPU noise to stderr and still exits 0**, so success is judged by exit code alone; and **`calibredb remove` deletes the row synchronously but its files in a background thread it does not wait for**, so removal is verified against the book directory and finished by hand. Replace runs **add-before-remove** — the surviving `Book` is repointed and committed before the old entry goes, so no crash window leaves a `Book` naming a `calibre_id` the next sync would answer by cascading it and its recipes away; any failure after the add takes the new entry back out. **Formats:** the library holds EPUB and PDF (`COOKMARKS_CALIBRE_SYNC_FORMATS`, and `LIBRARY_FORMATS` in the ingest service); everything else is converted to EPUB on the way in. `GET /api/books/{id}/file` serves whichever format a book has (EPUB wins when it holds both) and the in-app reader sniffs the bytes, so both read through the same foliate view. **Recipe extraction stays EPUB-only** — it walks the EPUB spine, so a PDF-only book gets a disabled Extract control, a 422 from the trigger endpoint, and `extraction_skipped` on an ingest run that asked for it (MY-148 fills the gap).
- Human-in-the-loop (MY-10): a file-method run that finds zero images pauses at the graph's `await_human` interrupt and goes `REVIEW`. The one question and its choices live in `app/services/extraction/review.py` (`REVIEW_QUESTION`, `REVIEW_CHOICES`, `VALID_HUMAN_RESPONSES`) — the single source shared by the graph (raises the interrupt), the resume path (validates the answer), and `ReviewQuestion` (surfaces it on the wire). With the live run view descoped, the book page reads the latest run via `GET /api/books/{id}/extraction` (`TaskRunRead | null`, with `pending_question` populated only while `REVIEW`); when it's paused, `BookDetail` shows the `ReviewPrompt` unit and `POST /api/books/{id}/extract/{run_id}/resume` dispatches the answer (`enqueue_resume_extraction`) — fire-and-forget, like the trigger. The full run history/reports view is the admin **Task Runs** tab on top of `TaskRunRead`.

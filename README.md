# cookmarks v2

A rebuild of Cookmarks on a typed-Python **FastAPI** backend and a **Svelte** SPA, with an
agent-verifiable harness at its core: every UI unit exposes a machine-readable DOM contract,
mounts in isolation, and is checked through one verdict taxonomy — the same code path drives
the dashboard, CI, and an AI agent driving a live browser.

## Stack

- **Backend** — FastAPI · SQLAlchemy 2.0 + Alembic · Celery · SQLite · uv · Python 3.11 (ruff, ty, pytest)
- **Frontend** — SvelteKit (adapter-static SPA) · Vite · TypeScript · Zod (vitest, svelte-check)
- **Serving** — dev: Vite `:9789` proxies `/api` → uvicorn `:9788`; prod: FastAPI serves the built SPA.

## Getting started

```sh
make install      # uv sync + npm install
make dev          # Vite (:5173) + uvicorn (:8000)
```

Open <http://localhost:9789> for the app and <http://localhost:9789/verify> for the
verification dashboard.

## Verification

```sh
make verify       # headless unit x fixture matrix (vitest)
make check        # ruff + ty + svelte-check
make test         # pytest + vitest
make build        # SPA -> frontend/build, served by FastAPI in prod
```

See [CLAUDE.md](./CLAUDE.md) for the harness design and the agent feedback loop.

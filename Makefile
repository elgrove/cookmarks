.PHONY: install dev dev-auto migrate build verify check test fmt eval

install:
	cd backend && uv sync
	cd frontend && npm install

# Apply Alembic migrations (the alembic console script isn't installed; use the module).
migrate:
	cd backend && uv run python -m alembic upgrade head

# Dev (trunk): Vite (:9789, HMR, proxies /api) + uvicorn (:9788). The agent's live loop.
dev:
	uvx honcho start

# Dev on a free port slot (2789, 3789, 4789 ...) so extra servers run side by side.
# Force one with `make dev-auto SLOT=5`; preview the pick with `scripts/dev.sh --print`.
dev-auto:
	./scripts/dev.sh $(SLOT)

# Headless verification matrix (units x fixtures). The agent's fast inner loop.
verify:
	cd frontend && npm run verify

# Production build: SPA -> frontend/build, served by FastAPI.
build:
	cd frontend && npm run build

check:
	cd backend && uv run ruff check . && uv run ty check
	cd frontend && npm run check

# Module form (python -m) over the bare `pytest` console script: immune to stale
# venv shebangs, exactly as `make migrate` uses `python -m alembic`.
test:
	cd backend && uv run python -m pytest
	cd frontend && npm run test

fmt:
	cd backend && uv run ruff format .

# Run the extraction eval against the gold cookbooks (real AI; see backend/evals).
# Scope with ARGS, e.g. `make eval ARGS="--model gemini-flash --book curry-guy"`.
# Summarise past runs without re-running: `uv run python -m evals report leaderboard`.
eval:
	cd backend && uv run python -m evals run $(ARGS)

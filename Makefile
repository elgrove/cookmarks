.PHONY: install dev migrate build verify check test fmt

install:
	cd backend && uv sync
	cd frontend && npm install

# Apply Alembic migrations (the alembic console script isn't installed; use the module).
migrate:
	cd backend && uv run python -m alembic upgrade head

# Dev: Vite (:9789, HMR, proxies /api) + uvicorn (:9788). The agent's live loop.
dev:
	uvx honcho start

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

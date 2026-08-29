---
name: deploy-prod
description: >-
  Deploy Cookmarks to the production self-hosted stack in ~/docker/cookmarks.
  Use this whenever the user asks to deploy, ship, release, redeploy, roll out,
  or "push to prod" for cookmarks — or to rebuild/restart the running prod
  container, apply the latest main to prod, or recover/roll back the prod
  deploy. The prod stack is a single Docker container (FastAPI + Celery + Redis
  under s6-overlay) built locally from this repo and serving on :8789. Reach for
  this skill even if the user only says "deploy it" while working in the
  cookmarks repo.
---

# Deploy Cookmarks to prod (~/docker/cookmarks)

Production is a **single container** built locally from this repo's `Dockerfile`
(SPA + FastAPI + Celery worker + Redis, supervised by s6-overlay), serving on
`:8789`. It lives at `~/docker/cookmarks/` alongside the user's other homelab
services. There is no registry — the image is built on the host from the working
copy at `/home/aaron/dev/cookmarks`.

## Critical environment facts

- **Deploy dir:** `~/docker/cookmarks/` — holds `docker-compose.yml` and `data/`.
- **Build context:** the compose `build.context` points at `/home/aaron/dev/cookmarks`,
  so the deploy ships **whatever is checked out there** (normally `main`). Make
  sure the repo is on the intended commit before building.
- **Data:** SQLite + sqlite-vec embeddings + the Redis dump persist on the
  `./data:/data` bind-mount (`data/db.sqlite3`). The schema is **auto-migrated on
  every container start** by the s6 `db-init` oneshot (`alembic upgrade head`) —
  you do not run migrations by hand for a routine deploy.
- **Calibre library:** Cookmarks' own, mounted **read-write** `./library:/library`
  (`~/docker/cookmarks/library`); the app resolves book paths under `/library` (env
  `COOKMARKS_CALIBRE_LIBRARY_PATH=/library`). It is a real library with its own
  `metadata.db`, written by book ingestion — **back it up alongside the DB**, and never
  let a second writer (a Calibre GUI, Syncthing) near it.
- **AI key:** stored in the DB `config` row, set via the settings UI — **not** an
  env secret. It survives across deploys because it lives on the data volume.
- **Health:** `GET http://localhost:8789/api/health` → `{"status":"ok",...}`.

## Sandbox caveat (important)

Docker and everything under `~/docker` may be **outside sandboxed writable/exec roots**,
so `docker ...`, `docker compose ...`, and any `cp`/`mv` into `~/docker` may fail with
permission denied if run in a restricted sandbox. Run deployment commands with direct host
execution permissions. Git operations in this repo are fine in standard workspace environments.

## Routine deploy

Use the bundled script — it does the safe sequence in one shot (build first for
near-zero downtime, consistent DB backup, recreate, verify):

```bash
~/dev/cookmarks/.agents/skills/deploy-prod/scripts/deploy.sh
```

It will:

1. **Pre-flight** — confirm the compose dir, docker, and the repo commit; print
   what's about to ship.
2. **Build** the new image while the old container keeps serving (no downtime yet).
3. **Back up the DB** with `sqlite3 .backup` (consistent even with WAL active)
   into `~/docker/cookmarks/backups/db-<timestamp>.sqlite3`, keeping the last 10 —
   and the **library catalogue** the same way, into
   `backups/metadata-<timestamp>.db`. The books themselves are hardlinked from
   `~/books/calibre-all` and need no copy; `metadata.db` is the part ingestion
   rewrites, and losing it would orphan every book.
4. **Recreate** the container (`docker compose up -d`) — brief restart; this is
   where `alembic upgrade head` runs against the volume DB.
5. **Verify** — wait for `healthy`, hit `/api/health`, tail recent logs.

If you'd rather drive it by hand, the equivalent steps:

```bash
cd ~/docker/cookmarks
docker compose build
sqlite3 data/db.sqlite3 ".backup 'backups/db-$(date +%Y%m%d-%H%M%S).sqlite3'"   # mkdir -p backups first
sqlite3 library/metadata.db ".backup 'backups/metadata-$(date +%Y%m%d-%H%M%S).db'"
docker compose up -d
# then poll: docker inspect --format '{{.State.Health.Status}}' cookmarks-cookmarks-1
curl -fsS http://localhost:8789/api/health
docker compose logs --tail 30
```

### Deploying the latest main

If the user wants prod to match the latest `main`, ensure the repo is current
**before** building (the build context is the working copy):

```bash
cd ~/dev/cookmarks && git checkout main && git pull --ff-only
```

Then run the deploy script.

## Smoke test after deploy

Health alone isn't enough — confirm the data layer and Calibre mount actually
serve. A quick pass (these are read-only and free — no AI calls):

```bash
curl -fsS localhost:8789/api/home                       # stats: books/recipes/keywords
curl -fsS "localhost:8789/api/recipes?q=chicken&limit=1"  # search hits (total > 0)
curl -fsS -o /dev/null -w '%{http_code} %{content_type}\n' \
  localhost:8789/api/books/<id>/cover                   # cover streams from /library
```

Note: bare `GET /api/recipes` with no query returns `{"total":0,"items":[]}` **by
design** (resting empty state) — that is not a failure.

## Rollback

The data volume and image are the two things to restore.

- **App code/image:** redeploy a known-good commit — `git checkout <sha>` in the
  repo, then re-run the deploy script (it rebuilds from the working copy).
- **Database:** stop the container, restore a backup over `data/db.sqlite3`
  (clear stale `-wal`/`-shm` first), then start again:

  ```bash
  cd ~/docker/cookmarks
  docker compose down
  rm -f data/db.sqlite3-wal data/db.sqlite3-shm
  cp backups/db-<timestamp>.sqlite3 data/db.sqlite3
  docker compose up -d
  ```

The previous compose file from the v2 cutover is preserved as
`~/docker/cookmarks/docker-compose.yml.v1-backup`.

## One-time: v1 (Django) → v2 (FastAPI) data migration

Only relevant when seeding a v2 DB from the **old Django** production database
(the v1→v2 cutover; already done once). The purpose-built script reads the v1
DB read-only and writes a v2-schema DB, preserving UUIDs, embeddings, lists,
favourites, and the API key:

```bash
cd ~/dev/cookmarks/backend && uv sync
export COOKMARKS_DB_PATH=/tmp/cookmarks-v2-build/db.sqlite3
uv run python -m alembic upgrade head
uv run python -m scripts.import_v1_data --source <path-to-v1-django-db.sqlite3>
# then move the built DB into ~/docker/cookmarks/data/db.sqlite3 (back up the old one first)
```

See `backend/scripts/import_v1_data.py` for the table mapping. The v1 prod DB
backups from the cutover are at `~/cookmarks-v1-db-backup/` and
`~/docker/cookmarks/data/db.sqlite3.v1-*`.

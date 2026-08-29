#!/usr/bin/env bash
# Deploy Cookmarks to the prod stack in ~/docker/cookmarks.
# Build first (no downtime), back up the DB consistently, recreate, verify.
# Run with the Claude sandbox disabled — docker and ~/docker are outside it.
set -euo pipefail

DEPLOY_DIR="${COOKMARKS_DEPLOY_DIR:-$HOME/docker/cookmarks}"
REPO_DIR="${COOKMARKS_REPO_DIR:-$HOME/dev/cookmarks}"
CONTAINER="cookmarks-cookmarks-1"
HEALTH_URL="http://localhost:8789/api/health"
KEEP_BACKUPS=10

cd "$DEPLOY_DIR"

echo "==> Pre-flight"
[ -f docker-compose.yml ] || { echo "no docker-compose.yml in $DEPLOY_DIR" >&2; exit 1; }
docker version >/dev/null || { echo "docker not reachable" >&2; exit 1; }
if [ -d "$REPO_DIR/.git" ]; then
  echo "    shipping repo: $(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD) @ $(git -C "$REPO_DIR" rev-parse --short HEAD)"
  if ! git -C "$REPO_DIR" diff --quiet || ! git -C "$REPO_DIR" diff --cached --quiet; then
    echo "    WARNING: working tree at $REPO_DIR is dirty — the build will include uncommitted changes"
  fi
fi

echo "==> Building image (old container keeps serving)"
docker compose build

echo "==> Backing up DB (consistent .backup, even with WAL)"
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
if [ -f data/db.sqlite3 ]; then
  sqlite3 data/db.sqlite3 ".backup 'backups/db-$STAMP.sqlite3'"
  echo "    -> backups/db-$STAMP.sqlite3 ($(du -h "backups/db-$STAMP.sqlite3" | cut -f1))"
  ls -1t backups/db-*.sqlite3 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
else
  echo "    no data/db.sqlite3 yet — skipping backup (fresh deploy)"
fi

# The library catalogue is rewritten by book ingestion, and losing it orphans every
# book. The book files themselves are hardlinked from ~/books/calibre-all — no copy.
if [ -f library/metadata.db ]; then
  sqlite3 library/metadata.db ".backup 'backups/metadata-$STAMP.db'"
  echo "    -> backups/metadata-$STAMP.db ($(du -h "backups/metadata-$STAMP.db" | cut -f1))"
  ls -1t backups/metadata-*.db 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f
else
  echo "    no library/metadata.db — skipping library backup"
fi

echo "==> Recreating container (runs alembic upgrade head on start)"
docker compose up -d

echo "==> Waiting for healthy"
for i in $(seq 1 30); do
  s=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "missing")
  echo "    [$i] health=$s"
  [ "$s" = "healthy" ] && break
  [ "$s" = "unhealthy" ] && { echo "container went unhealthy" >&2; docker compose logs --tail 40; exit 1; }
  sleep 3
done

echo "==> Verifying"
curl -fsS "$HEALTH_URL"; echo
curl -s -o /dev/null -w "    /api/home HTTP %{http_code}\n" http://localhost:8789/api/home


echo "==> Recent logs"
docker compose logs --tail 15

echo "==> Deploy complete."

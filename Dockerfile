# Cookmarks v2 — single-container image.
#
# One container runs the whole stack (Redis, FastAPI/uvicorn serving the API and
# the built SPA, and a Celery worker) under s6-overlay process supervision. The
# SPA is built in a separate stage and copied into the backend's static dir, so
# the running image carries no Node toolchain.

# Stage 1: build the Svelte SPA -> frontend/build
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: fetch the s6-overlay tarballs (multi-arch)
FROM alpine AS s6-stage
ARG S6_OVERLAY_VERSION=3.2.0.2
RUN apk add --no-cache wget
RUN wget -q "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz" -O /s6-noarch.tar.xz \
    && wget -q "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz" -O /s6-x86_64.tar.xz \
    && wget -q "https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-aarch64.tar.xz" -O /s6-aarch64.tar.xz

# Stage 3: Python backend + Redis + s6-overlay
FROM python:3.11-slim AS runtime
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    sqlite3 \
    xz-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install backend dependencies first (cached unless the lockfile changes).
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-cache --no-dev

# Backend source.
COPY backend/app/ ./app/
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/

# Built SPA -> served by FastAPI (COOKMARKS_FRONTEND_DIST points here).
COPY --from=frontend-build /app/frontend/build ./static/frontend

# Install s6-overlay.
COPY --from=s6-stage /s6-noarch.tar.xz /s6-x86_64.tar.xz /s6-aarch64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-noarch.tar.xz \
    && if [ "$TARGETARCH" = "arm64" ]; then \
         tar -C / -Jxpf /tmp/s6-aarch64.tar.xz; \
       else \
         tar -C / -Jxpf /tmp/s6-x86_64.tar.xz; \
       fi \
    && rm /tmp/s6-*.tar.xz

# Service definitions.
COPY docker/s6/ /etc/s6-overlay/

ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    PYTHONUNBUFFERED=1 \
    COOKMARKS_ENV=prod \
    COOKMARKS_DB_PATH=/data/db.sqlite3 \
    COOKMARKS_FRONTEND_DIST=/app/static/frontend

EXPOSE 8789

ENTRYPOINT ["/init"]

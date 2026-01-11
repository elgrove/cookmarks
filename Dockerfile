# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ENV UV_CACHE_DIR=/app/.cache

RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY uv.lock pyproject.toml ./
RUN uv sync --no-cache --frozen --no-dev

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY supervisord.conf /app/supervisord.conf

COPY . .

RUN uv run python manage.py collectstatic --no-input

EXPOSE 8789

ENTRYPOINT ["/entrypoint.sh"]
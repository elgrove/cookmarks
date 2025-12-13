#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
uv run python manage.py migrate

# Run supervisord to manage both app and worker
exec supervisord -c /app/supervisord.conf

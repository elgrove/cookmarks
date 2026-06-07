redis: redis-server --save '' --appendonly no --port ${COOKMARKS_REDIS_PORT:-6379}
api: cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port ${COOKMARKS_API_PORT:-9788}
web: cd frontend && VITE_DEV_PORT=${COOKMARKS_WEB_PORT:-9789} VITE_API_PROXY=http://localhost:${COOKMARKS_API_PORT:-9788} npm run dev
worker: cd backend && uv run celery -A app.tasks.celery_app:celery_app worker --loglevel=info --concurrency=1

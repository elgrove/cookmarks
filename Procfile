redis: redis-server --save '' --appendonly no
api: cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 9788
web: cd frontend && npm run dev
worker: cd backend && uv run celery -A app.tasks.celery_app:celery_app worker --loglevel=info --concurrency=1

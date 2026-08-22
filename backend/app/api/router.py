from fastapi import APIRouter, Depends

from app.api import (
    auth,
    books,
    config,
    extraction,
    game,
    health,
    home,
    ingest,
    lists,
    reading_queue,
    recipes,
    task_runs,
    tasks,
    tickets,
    users,
)
from app.api.deps import current_user, require_admin

# The single gate map for the API: health and the auth routes are open, everything else
# needs a session, and the admin surfaces need an admin. A handful of admin-only routes
# live inside otherwise user-level modules and carry their own route-level dependency
# (book delete, the extraction trigger and resume).
_USER = [Depends(current_user)]
_ADMIN = [Depends(require_admin)]

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(books.router, dependencies=_USER)
api_router.include_router(extraction.router, dependencies=_USER)
api_router.include_router(game.router, dependencies=_USER)
api_router.include_router(home.router, dependencies=_USER)
api_router.include_router(recipes.router, dependencies=_USER)
api_router.include_router(lists.router, dependencies=_USER)
api_router.include_router(reading_queue.router, dependencies=_USER)
api_router.include_router(tickets.router, dependencies=_USER)
api_router.include_router(config.router, dependencies=_ADMIN)
api_router.include_router(ingest.router, dependencies=_ADMIN)
api_router.include_router(tasks.router, dependencies=_ADMIN)
api_router.include_router(task_runs.router, dependencies=_ADMIN)
api_router.include_router(users.router, dependencies=_ADMIN)

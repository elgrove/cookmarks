from fastapi import APIRouter

from app.api import (
    books,
    config,
    extraction,
    health,
    home,
    lists,
    recipes,
    task_runs,
    tasks,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(books.router)
api_router.include_router(extraction.router)
api_router.include_router(home.router)
api_router.include_router(recipes.router)
api_router.include_router(lists.router)
api_router.include_router(config.router)
api_router.include_router(tasks.router)
api_router.include_router(task_runs.router)

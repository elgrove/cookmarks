from fastapi import APIRouter

from app.api import books, health, home, recipes

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(books.router)
api_router.include_router(home.router)
api_router.include_router(recipes.router)

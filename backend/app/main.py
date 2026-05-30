from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.static import mount_spa


def create_app() -> FastAPI:
    app = FastAPI(title="Cookmarks", version=settings.version)
    app.include_router(api_router)
    mount_spa(app, settings.frontend_dist)
    return app


app = create_app()

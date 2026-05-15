from ninja import NinjaAPI

from core.api.auth import session_auth
from core.api.routers.auth import router as auth_router
from core.api.routers.books import router as books_router
from core.api.routers.config import router as config_router
from core.api.routers.extraction import router as extraction_router
from core.api.routers.keywords import router as keywords_router
from core.api.routers.lists import router as lists_router
from core.api.routers.recipes import router as recipes_router
from core.api.routers.stats import router as stats_router
from core.api.routers.tasks import router as tasks_router

api = NinjaAPI(
    title="Cookmarks API",
    version="1.0.0",
    auth=session_auth,
)

api.add_router("/auth", auth_router, auth=None)
api.add_router("/books", books_router)
api.add_router("/recipes", recipes_router)
api.add_router("/lists", lists_router)
api.add_router("/keywords", keywords_router)
api.add_router("/tasks", tasks_router)
api.add_router("/config", config_router)
api.add_router("/extraction-reports", extraction_router)
api.add_router("/stats", stats_router)

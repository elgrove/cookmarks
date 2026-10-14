from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import Receive, Scope, Send

from app.api.router import api_router
from app.config import settings
from app.static import mount_spa

# Responses that are already compressed: gzipping them again only burns CPU.
# Matched on the request path — the three binary API endpoints by their tail,
# hashed SPA assets by file extension.
_BINARY_PATH_TAILS = ("/cover", "/file", "/image", "/thumb", "/thumbnail")
_BINARY_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".avif",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".pdf",
    ".epub",
)


class SelectiveGZipMiddleware(GZipMiddleware):
    """GZip for text and JSON only. Covers, book files and recipe images skip
    compression — MY-178: the server was gzipping multi-MB JPEGs per request."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.endswith(_BINARY_PATH_TAILS) or path.endswith(_BINARY_EXTENSIONS):
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


def create_app() -> FastAPI:
    app = FastAPI(title="Cookmarks", version=settings.version)
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=1000)
    app.include_router(api_router)
    mount_spa(app, settings.frontend_dist)
    return app


app = create_app()

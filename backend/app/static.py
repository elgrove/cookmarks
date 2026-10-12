from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse


def mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built Svelte SPA with a catch-all fallback to index.html.

    Registered after the API router so /api/* keeps precedence. Real asset paths
    are served from disk; everything else returns index.html so client-side deep
    links such as /verify/<unit>/<fixture> resolve.
    """
    if not dist.exists():
        return

    index = dist / "index.html"

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = (dist / full_path).resolve()
        if full_path and dist in candidate.parents and candidate.is_file():
            # Hashed build output keeps its hash across deploys, so a client can
            # cache it for a year. index.html itself carries no such header —
            # it must revalidate, or clients would pin a stale bundle. MY-178.
            if full_path.startswith("_app/immutable/"):
                headers = {"Cache-Control": "public, max-age=31536000, immutable"}
            else:
                headers = {"Cache-Control": "no-cache"}
            return FileResponse(candidate, headers=headers)
        # Entry HTML revalidates every load so clients never pin a stale bundle.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

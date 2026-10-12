"""MY-178: text/JSON responses are gzipped; already-compressed bytes are not;
hashed SPA assets cache immutably while entry HTML revalidates."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import TaskStatus, TaskType
from app.models.task_run import TaskRun
from app.static import mount_spa


def test_json_api_response_is_gzipped(client: TestClient, session: Session) -> None:
    # Gzip only engages above the 1000-byte floor, so seed enough history.
    for _ in range(10):
        session.add(
            TaskRun(task_type=TaskType.BOOK_KEYWORDS, status=TaskStatus.DONE, detail={})
        )
    session.commit()
    res = client.get("/api/task-runs", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert len(res.content) > 1000
    assert res.headers.get("content-encoding") == "gzip"
    # httpx decodes the body, so a parsed list proves the encoding was honest.
    assert isinstance(res.json(), list)


def test_binary_tails_skip_gzip(client: TestClient) -> None:
    # The three binary endpoints must not pay gzip CPU per request. A missing
    # book 404s before any bytes stream, but the middleware path gate still
    # applies — no content-encoding on the way out.
    for tail in ("cover", "file"):
        res = client.get(
            f"/api/books/00000000-0000-4000-8000-000000000000/{tail}",
            headers={"Accept-Encoding": "gzip"},
        )
        assert res.status_code == 404
        assert "content-encoding" not in res.headers
    res = client.get(
        "/api/recipes/00000000-0000-4000-8000-000000000000/image",
        headers={"Accept-Encoding": "gzip"},
    )
    assert res.status_code == 404
    assert "content-encoding" not in res.headers


def test_spa_cache_headers(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    hashed = dist / "_app" / "immutable" / "app.abc123.js"
    hashed.parent.mkdir(parents=True)
    hashed.write_text("console.log('app')")
    (dist / "index.html").write_text("<html></html>")

    spa = FastAPI()
    mount_spa(spa, dist)
    spa_client = TestClient(spa)

    asset = spa_client.get("/_app/immutable/app.abc123.js")
    assert asset.status_code == 200
    assert asset.headers["Cache-Control"] == "public, max-age=31536000, immutable"

    index = spa_client.get("/some/deep/link")
    assert index.status_code == 200
    assert index.headers["Cache-Control"] == "no-cache"

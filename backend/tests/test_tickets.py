from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.config import settings
from app.main import app
from app.models import User
from app.services.linear import LinearError

client = TestClient(app)


@pytest.fixture(autouse=True)
def _signed_in() -> Iterator[None]:
    """These routes are DB-free, so this module drives the app without the `client`
    fixture — it still needs a signed-in caller, since /api/tickets is gated."""
    app.dependency_overrides[current_user] = lambda: User(
        username="tester", password_hash="!", is_admin=False
    )
    yield
    app.dependency_overrides.clear()


def test_tickets_disabled_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "linear_api_key", "")
    monkeypatch.setattr(settings, "linear_team_id", "")
    assert client.get("/api/tickets/enabled").json() == {"enabled": False}


def test_tickets_enabled_when_key_and_team_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "linear_api_key", "lin_key")
    monkeypatch.setattr(settings, "linear_team_id", "team-id")
    assert client.get("/api/tickets/enabled").json() == {"enabled": True}


def test_submit_ticket_files_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_create_issue(title: str, description: str) -> dict[str, str]:
        captured["title"] = title
        captured["description"] = description
        return {"identifier": "MY-42", "url": "https://linear.app/issue/MY-42"}

    monkeypatch.setattr("app.api.tickets.create_issue", fake_create_issue)

    resp = client.post(
        "/api/tickets",
        json={
            "title": "  Search is broken  ",
            "description": "  no results  ",
            "page_url": "http://localhost/recipes",
        },
    )

    assert resp.status_code == 201
    assert resp.json() == {"identifier": "MY-42", "url": "https://linear.app/issue/MY-42"}
    # Title is trimmed, and the originating page is appended to the description.
    assert captured["title"] == "Search is broken"
    assert "no results" in captured["description"]
    assert "http://localhost/recipes" in captured["description"]


def test_submit_ticket_rejects_blank_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.tickets.create_issue",
        lambda *_a, **_k: pytest.fail("should not reach Linear for a blank title"),
    )
    resp = client.post("/api/tickets", json={"title": "   "})
    assert resp.status_code == 422


def test_submit_ticket_surfaces_linear_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_title: str, _description: str) -> dict[str, str]:
        raise LinearError("Could not reach Linear")

    monkeypatch.setattr("app.api.tickets.create_issue", boom)
    resp = client.post("/api/tickets", json={"title": "Anything"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Could not reach Linear"

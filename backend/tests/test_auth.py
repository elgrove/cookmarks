"""The real auth path. These clear conftest's `current_user` override so requests go
through the cookie, unlike the rest of the suite which runs as the seeded admin."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.main import app
from app.models import Book, User
from app.services.auth import COOKIE_NAME
from app.services.users import create_user
from tests.conftest import TESTER_PASSWORD


@pytest.fixture
def anon(client: TestClient) -> Iterator[TestClient]:
    """The same client with the auth override removed — nobody is logged in."""
    app.dependency_overrides.pop(current_user, None)
    yield client


def test_login_sets_a_cookie_and_me_succeeds(anon: TestClient) -> None:
    res = anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    assert res.status_code == 200
    assert res.json()["username"] == "tester"
    assert COOKIE_NAME in res.cookies
    me = anon.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "id": res.json()["id"],
        "username": "tester",
        "is_admin": True,
        "auth_mode": "session",
        "cooking_instructions": None,
    }


def test_wrong_password_is_rejected_without_a_cookie(anon: TestClient) -> None:
    res = anon.post("/api/auth/login", json={"username": "tester", "password": "nope"})
    assert res.status_code == 401
    assert COOKIE_NAME not in res.cookies
    assert anon.get("/api/auth/me").status_code == 401


def test_unknown_user_gets_the_same_generic_message(anon: TestClient) -> None:
    known = anon.post("/api/auth/login", json={"username": "tester", "password": "nope"})
    unknown = anon.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == known.json()["detail"]


def test_me_without_a_cookie_is_401(anon: TestClient) -> None:
    assert anon.get("/api/auth/me").status_code == 401


def test_logout_invalidates_the_session(anon: TestClient) -> None:
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    assert anon.post("/api/auth/logout").status_code == 204
    assert anon.get("/api/auth/me").status_code == 401


def test_auth_mode_none_needs_no_cookie(
    anon: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.deps.settings.auth_mode", "none")
    monkeypatch.setattr("app.api.auth.settings.auth_mode", "none")
    body = anon.get("/api/auth/me").json()
    assert body["auth_mode"] == "none"
    # The implicit user is the oldest account — the seeded tester, not a new one.
    assert body["username"] == "tester"


def test_reads_require_a_session(anon: TestClient) -> None:
    assert anon.get("/api/books").status_code == 401


def test_non_admin_reads_but_cannot_reach_admin_surfaces(
    anon: TestClient, session: Session
) -> None:
    create_user(session, "plain", "plain-password", is_admin=False)
    assert anon.post(
        "/api/auth/login", json={"username": "plain", "password": "plain-password"}
    ).status_code == 200

    assert anon.get("/api/books").status_code == 200
    assert anon.get("/api/config").status_code == 403
    assert anon.get("/api/task-runs").status_code == 403
    assert anon.get("/api/users").status_code == 403

    book_id = session.scalar(select(Book.id))
    assert anon.delete(f"/api/books/{book_id}").status_code == 403
    assert anon.post(f"/api/books/{book_id}/extract").status_code == 403
    # Adding a book writes to the library and downloads from the internet — admin only.
    staging = anon.post("/api/ingest/stage/url", json={"url": "https://example.com/x"})
    assert staging.status_code == 403
    confirm = anon.post("/api/ingest", json={"staging_id": "x", "title": "t", "author": "a"})
    assert confirm.status_code == 403


def test_admin_reaches_admin_surfaces(anon: TestClient) -> None:
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    assert anon.get("/api/config").status_code == 200
    assert anon.get("/api/users").status_code == 200


def test_health_stays_open(anon: TestClient) -> None:
    assert anon.get("/api/health").status_code == 200


def test_password_reset_swaps_the_working_password(anon: TestClient, session: Session) -> None:
    user = create_user(session, "plain", "old-password")
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    assert anon.post(
        f"/api/users/{user.id}/password", json={"password": "new-password"}
    ).status_code == 204
    anon.post("/api/auth/logout")
    assert anon.post(
        "/api/auth/login", json={"username": "plain", "password": "old-password"}
    ).status_code == 401
    assert anon.post(
        "/api/auth/login", json={"username": "plain", "password": "new-password"}
    ).status_code == 200


def test_session_survives_a_second_request(anon: TestClient, session: Session) -> None:
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    assert session.scalar(select(User).where(User.username == "tester")) is not None
    assert anon.get("/api/lists").status_code == 200
    assert anon.get("/api/lists").status_code == 200


def test_update_cooking_instructions(anon: TestClient) -> None:
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    res = anon.patch("/api/auth/me", json={"cooking_instructions": "No coriander."})
    assert res.status_code == 200
    assert res.json()["cooking_instructions"] == "No coriander."
    me = anon.get("/api/auth/me")
    assert me.json()["cooking_instructions"] == "No coriander."


def test_update_cooking_instructions_length_limit(anon: TestClient) -> None:
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    res = anon.patch("/api/auth/me", json={"cooking_instructions": "x" * 4001})
    assert res.status_code == 422


def test_cooking_instructions_are_private_between_users(
    anon: TestClient, session: Session
) -> None:
    create_user(session, "user1", "password123")
    create_user(session, "user2", "password456")
    anon.post("/api/auth/login", json={"username": "user1", "password": "password123"})
    anon.patch("/api/auth/me", json={"cooking_instructions": "Diet: vegan."})
    anon.post("/api/auth/logout")

    anon.post("/api/auth/login", json={"username": "user2", "password": "password456"})
    me2 = anon.get("/api/auth/me").json()
    assert me2["cooking_instructions"] is None

    anon.post("/api/auth/logout")
    anon.post("/api/auth/login", json={"username": "tester", "password": TESTER_PASSWORD})
    users = anon.get("/api/users").json()
    for u in users:
        assert "cooking_instructions" not in u


from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GameDismissal, User
from app.services.users import create_user


def _all_recipe_ids(client: TestClient) -> list[str]:
    items = client.get("/api/recipes", params={"all": "true", "seed": 1}).json()["items"]
    return [item["id"] for item in items]


def _eligible(client: TestClient, recipe_ids: list[str]) -> list[str]:
    resp = client.post("/api/game/eligible", json={"recipe_ids": recipe_ids})
    assert resp.status_code == 200
    return resp.json()["recipe_ids"]


def test_all_param_returns_every_recipe(client: TestClient) -> None:
    resp = client.get("/api/recipes", params={"all": "true"}).json()
    assert resp["total"] == 3
    assert len(resp["items"]) == 3


def test_resting_state_without_all_param(client: TestClient) -> None:
    resp = client.get("/api/recipes").json()
    assert resp == {"total": 0, "items": [], "facets": []}


def test_eligible_preserves_input_order(client: TestClient) -> None:
    ids = list(reversed(_all_recipe_ids(client)))
    assert _eligible(client, ids) == ids


def test_eligible_excludes_favourited(client: TestClient) -> None:
    ids = _all_recipe_ids(client)
    client.post(f"/api/recipes/{ids[0]}/favourite")
    assert _eligible(client, ids) == ids[1:]


def test_eligible_excludes_dismissed(client: TestClient) -> None:
    ids = _all_recipe_ids(client)
    client.put(f"/api/game/dismissals/{ids[1]}")
    assert _eligible(client, ids) == [ids[0], *ids[2:]]


def test_dismiss_is_idempotent(client: TestClient, session: Session) -> None:
    recipe_id = _all_recipe_ids(client)[0]
    for _ in range(2):
        resp = client.put(f"/api/game/dismissals/{recipe_id}")
        assert resp.status_code == 200
        assert resp.json() == {"dismissed": True}
    assert len(session.scalars(select(GameDismissal)).all()) == 1


def test_dismiss_unknown_recipe_404s(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.put(f"/api/game/dismissals/{missing}").status_code == 404


def test_dismissals_are_per_user(
    client: TestClient, session: Session, act_as: Callable[[str], User]
) -> None:
    ids = _all_recipe_ids(client)
    client.put(f"/api/game/dismissals/{ids[0]}")
    create_user(session, "other", "other-password")
    act_as("other")
    assert _eligible(client, ids) == ids

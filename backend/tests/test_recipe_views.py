import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Recipe, RecipeView
from app.services.views import VIEW_WINDOW

EXPECTED_KEYS = {"view_count", "first_viewed_at", "last_viewed_at"}


def _recipe_id(session: Session) -> uuid.UUID:
    recipe = session.scalar(select(Recipe).where(Recipe.name == "Recipe 0"))
    assert recipe is not None
    return recipe.id


def test_first_view_creates_the_record(client: TestClient, session: Session) -> None:
    resp = client.post(f"/api/recipes/{_recipe_id(session)}/seen")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == EXPECTED_KEYS
    assert body["view_count"] == 1
    assert session.scalar(select(RecipeView.view_count)) == 1


def test_second_view_inside_the_window_only_moves_the_timestamp(
    client: TestClient, session: Session
) -> None:
    recipe_id = _recipe_id(session)
    first = client.post(f"/api/recipes/{recipe_id}/seen").json()
    second = client.post(f"/api/recipes/{recipe_id}/seen").json()
    assert second["view_count"] == 1
    assert second["first_viewed_at"] == first["first_viewed_at"]
    assert second["last_viewed_at"] >= first["last_viewed_at"]
    # Still exactly one row per (user, recipe).
    assert len(session.scalars(select(RecipeView)).all()) == 1


def test_view_after_the_window_bumps_the_count(client: TestClient, session: Session) -> None:
    recipe_id = _recipe_id(session)
    client.post(f"/api/recipes/{recipe_id}/seen")
    view = session.scalar(select(RecipeView))
    assert view is not None
    view.last_viewed_at = datetime.now(UTC) - VIEW_WINDOW - timedelta(minutes=1)
    session.commit()

    assert client.post(f"/api/recipes/{recipe_id}/seen").json()["view_count"] == 2


def test_unmarking_forgets_the_view(client: TestClient, session: Session) -> None:
    recipe_id = _recipe_id(session)
    client.post(f"/api/recipes/{recipe_id}/seen")

    assert client.delete(f"/api/recipes/{recipe_id}/seen").status_code == 204
    assert session.scalars(select(RecipeView)).all() == []

    # Reading it again starts a fresh record rather than resuming the old count.
    assert client.post(f"/api/recipes/{recipe_id}/seen").json()["view_count"] == 1


def test_unmarking_an_unread_recipe_is_a_no_op(client: TestClient, session: Session) -> None:
    assert client.delete(f"/api/recipes/{_recipe_id(session)}/seen").status_code == 204


def test_views_are_recorded_without_being_reported_back(client: TestClient, session: Session) -> None:
    """Views keep being collected — they feed a book's reading — but a recipe carries
    no read state of its own on the wire any more."""
    recipe_id = _recipe_id(session)
    assert "is_seen" not in client.get(f"/api/recipes/{recipe_id}").json()
    client.post(f"/api/recipes/{recipe_id}/seen")
    assert session.scalars(select(RecipeView)).all() != []


def test_unknown_recipe_is_404(client: TestClient) -> None:
    assert client.post(f"/api/recipes/{uuid.uuid4()}/seen").status_code == 404
    assert client.delete(f"/api/recipes/{uuid.uuid4()}/seen").status_code == 404

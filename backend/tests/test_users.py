import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import RecipeList, User
from app.services.auth import create_session, resolve_session
from app.services.users import UserError, create_user, delete_user, set_password


def test_create_list_delete_round_trip(client: TestClient) -> None:
    created = client.post(
        "/api/users", json={"username": "second", "password": "second-password", "is_admin": False}
    )
    assert created.status_code == 201
    body = created.json()
    assert body["username"] == "second" and body["is_admin"] is False

    usernames = [u["username"] for u in client.get("/api/users").json()]
    assert usernames == ["tester", "second"]

    assert client.delete(f"/api/users/{body['id']}").status_code == 204
    assert [u["username"] for u in client.get("/api/users").json()] == ["tester"]


def test_duplicate_username_is_409(client: TestClient) -> None:
    client.post("/api/users", json={"username": "second", "password": "second-password"})
    again = client.post("/api/users", json={"username": "second", "password": "second-password"})
    assert again.status_code == 409


def test_deleting_the_last_admin_is_409(client: TestClient, session: Session) -> None:
    # Another (non-admin) account exists, so this is about admin count, not user count.
    other = create_user(session, "plain", "plain-password")
    assert client.delete(f"/api/users/{other.id}").status_code == 204
    admin = session.scalar(select(User).where(User.username == "tester"))
    assert admin is not None
    with pytest.raises(UserError):
        delete_user(session, admin)


def test_deleting_yourself_is_409(client: TestClient, session: Session) -> None:
    me = session.scalar(select(User).where(User.username == "tester"))
    assert me is not None
    res = client.delete(f"/api/users/{me.id}")
    assert res.status_code == 409


def test_deleting_a_user_takes_their_lists(client: TestClient, session: Session) -> None:
    other = create_user(session, "plain", "plain-password")
    session.add(RecipeList(name="Theirs", user_id=other.id))
    session.commit()
    assert client.delete(f"/api/users/{other.id}").status_code == 204
    session.expire_all()
    assert session.scalar(select(RecipeList).where(RecipeList.user_id == other.id)) is None


def test_first_user_adopts_orphan_lists(session: Session) -> None:
    # A pre-accounts deployment: lists with no owner. conftest seeds one user already,
    # so start from a table where that seeded account is removed.
    session.execute(delete(RecipeList))
    session.execute(delete(User))
    session.add(RecipeList(name="Favourites", is_default=True))
    session.commit()

    first = create_user(session, "aaron", "aaron-password", is_admin=True)
    session.expire_all()
    adopted = session.scalar(select(RecipeList).where(RecipeList.name == "Favourites"))
    assert adopted is not None and adopted.user_id == first.id


def test_a_later_user_adopts_nothing(session: Session) -> None:
    session.execute(delete(RecipeList))
    session.execute(delete(User))
    first = create_user(session, "aaron", "aaron-password", is_admin=True)
    session.add(RecipeList(name="Favourites", is_default=True, user_id=first.id))
    session.add(RecipeList(name="Orphan", is_default=False))
    session.commit()

    create_user(session, "second", "second-password")
    session.expire_all()
    orphan = session.scalar(select(RecipeList).where(RecipeList.name == "Orphan"))
    assert orphan is not None and orphan.user_id is None


def test_password_reset_signs_the_account_out_everywhere(
    client: TestClient, session: Session
) -> None:
    """A reset is how a compromised account is taken back — the old cookies must die."""
    user = create_user(session, "plain", "old-password")
    token = create_session(session, user)
    set_password(session, user, "new-password")
    assert resolve_session(session, token) is None


def test_the_first_account_is_always_an_admin(session: Session) -> None:
    session.execute(delete(RecipeList))
    session.execute(delete(User))
    session.commit()
    first = create_user(session, "aaron", "aaron-password", is_admin=False)
    assert first.is_admin


def test_short_passwords_are_rejected(client: TestClient, session: Session) -> None:
    res = client.post("/api/users", json={"username": "second", "password": "short"})
    assert res.status_code == 409
    with pytest.raises(UserError):
        create_user(session, "third", "short")


def test_usernames_collide_case_insensitively(client: TestClient) -> None:
    client.post("/api/users", json={"username": "Second", "password": "second-password"})
    again = client.post("/api/users", json={"username": "second", "password": "second-password"})
    assert again.status_code == 409

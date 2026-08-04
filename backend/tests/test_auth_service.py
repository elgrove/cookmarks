from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user import User, UserSession
from app.services.auth import (
    create_session,
    delete_session,
    hash_password,
    resolve_session,
    verify_password,
)
from app.services.users import implicit_user


def _user(session: Session, username: str = "sessions-tester") -> User:
    user = User(username=username, password_hash=hash_password("correct horse"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_password_round_trip() -> None:
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)


def test_hashes_are_salted() -> None:
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_never_verifies() -> None:
    assert not verify_password("anything", "!")
    assert not verify_password("anything", "scrypt$nope")


def test_session_round_trip(session: Session) -> None:
    user = _user(session)
    token = create_session(session, user)
    # The raw token is never stored — only its sha256.
    assert session.scalar(select(UserSession.token_hash)) != token
    resolved = resolve_session(session, token)
    assert resolved is not None and resolved.id == user.id


def test_expired_session_resolves_to_none(session: Session) -> None:
    user = _user(session)
    token = create_session(session, user)
    row = session.scalar(select(UserSession))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert resolve_session(session, token) is None
    # ... and the dead row is cleaned up on the way past.
    assert session.scalar(select(UserSession)) is None


def test_unknown_token_resolves_to_none(session: Session) -> None:
    _user(session)
    assert resolve_session(session, "not-a-real-token") is None


def test_delete_session_invalidates(session: Session) -> None:
    user = _user(session)
    token = create_session(session, user)
    delete_session(session, token)
    assert resolve_session(session, token) is None


def test_implicit_user_is_the_existing_account(session: Session) -> None:
    """With accounts already present (conftest seeds one) the implicit user is the
    oldest of them, so switching a deployment to auth_mode="none" loses no state."""
    before = len(session.scalars(select(User)).all())
    first = implicit_user(session)
    second = implicit_user(session)
    assert first.id == second.id
    assert first.username == "tester"
    assert len(session.scalars(select(User)).all()) == before


def test_implicit_user_is_created_once_on_an_empty_table(session: Session) -> None:
    session.execute(delete(User))
    session.commit()
    first = implicit_user(session)
    second = implicit_user(session)
    assert first.id == second.id
    assert first.is_admin
    assert len(session.scalars(select(User)).all()) == 1
    # An unusable hash: no password can ever log this account in.
    assert not verify_password("", first.password_hash)

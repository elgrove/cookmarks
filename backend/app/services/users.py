"""Account lifecycle: create, delete, reset password, and the implicit user of
`auth_mode="none"`. The guards here (unique username, a minimum password, never remove
the last admin) are enforced in one place so the API and the seeding script cannot drift
apart."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.recipe_list import RecipeList
from app.models.user import User
from app.services.auth import UNUSABLE_PASSWORD, delete_sessions_for, hash_password

# Low enough not to be theatre on a LAN-only deployment, high enough that a one-character
# password can't be set from the admin UI.
MIN_PASSWORD_LENGTH = 8


class UserError(Exception):
    """A rejected account operation — the API maps this to a 409."""


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(f"A password of at least {MIN_PASSWORD_LENGTH} characters is required.")


def _adopt_orphan_lists(session: Session, user_id: uuid.UUID) -> None:
    """Carry a pre-accounts deployment's Favourites and lists over to its first owner."""
    session.execute(update(RecipeList).where(RecipeList.user_id.is_(None)).values(user_id=user_id))
    session.commit()


def _is_first_user(session: Session) -> bool:
    return session.scalar(select(func.count()).select_from(User)) == 0


def create_user(session: Session, username: str, password: str, is_admin: bool = False) -> User:
    username = username.strip()
    if not username:
        raise UserError("A username is required.")
    _check_password(password)
    # Case-insensitive: "Aaron" and "aaron" would otherwise be two accounts that look
    # like one, and the column's UNIQUE wouldn't catch it.
    existing = session.scalar(
        select(User).where(func.lower(User.username) == username.lower())
    )
    if existing is not None:
        raise UserError("That username is already taken.")
    # The first account is always an admin: /api/users is admin-gated, so a deployment
    # whose only account isn't one has no in-app route back.
    first_user = _is_first_user(session)
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_admin=is_admin or first_user,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise UserError("That username is already taken.") from exc
    session.refresh(user)
    if first_user:
        _adopt_orphan_lists(session, user.id)
    return user


def delete_user(session: Session, user: User) -> None:
    if user.is_admin:
        admins = session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        if (admins or 0) <= 1:
            raise UserError("The last admin cannot be deleted.")
    session.delete(user)
    session.commit()


def set_password(session: Session, user: User, password: str) -> None:
    _check_password(password)
    user.password_hash = hash_password(password)
    session.commit()
    # A reset is how a compromised or handed-over account is taken back; leaving the old
    # 30-day cookies alive would defeat it.
    delete_sessions_for(session, user.id)


def implicit_user(session: Session) -> User:
    """The single user every request resolves to under `auth_mode="none"`: the oldest
    account, or a freshly created `default` admin on an empty table — which adopts the
    pre-accounts lists exactly as a first real account would, so an upgraded deployment
    keeps its Favourites either way."""
    user = session.scalar(select(User).order_by(User.created_at).limit(1))
    if user is not None:
        return user
    first_user = _is_first_user(session)
    user = User(username="default", password_hash=UNUSABLE_PASSWORD, is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    if first_user:
        _adopt_orphan_lists(session, user.id)
    return user

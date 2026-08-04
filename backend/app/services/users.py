"""Account lifecycle: create, delete, reset password. The guards here (unique username,
never remove the last admin) are enforced in one place so the API and the seeding script
cannot drift apart."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.recipe_list import RecipeList
from app.models.user import User
from app.services.auth import hash_password


class UserError(Exception):
    """A rejected account operation — the API maps this to a 409."""


def create_user(session: Session, username: str, password: str, is_admin: bool = False) -> User:
    username = username.strip()
    if not username:
        raise UserError("username is required")
    if not password:
        raise UserError("password is required")
    if session.scalar(select(User).where(User.username == username)) is not None:
        raise UserError("that username is already taken")
    first_user = session.scalar(select(func.count()).select_from(User)) == 0
    user = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    session.add(user)
    session.commit()
    session.refresh(user)
    if first_user:
        # Carry a pre-accounts deployment's Favourites and lists over to its owner.
        session.execute(
            update(RecipeList).where(RecipeList.user_id.is_(None)).values(user_id=user.id)
        )
        session.commit()
    return user


def delete_user(session: Session, user: User) -> None:
    if user.is_admin:
        admins = session.scalar(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        if (admins or 0) <= 1:
            raise UserError("the last admin cannot be deleted")
    session.delete(user)
    session.commit()


def set_password(session: Session, user: User, password: str) -> None:
    if not password:
        raise UserError("password is required")
    user.password_hash = hash_password(password)
    session.commit()

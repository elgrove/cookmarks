import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUIDAuditBase


class User(UUIDAuditBase):
    """An account that can log in. Personal state (lists, favourites) hangs off this."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)


class UserSession(UUIDAuditBase):
    """A logged-in browser session. `token_hash` is sha256 of the cookie value, so a
    stolen database does not hand over live sessions."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

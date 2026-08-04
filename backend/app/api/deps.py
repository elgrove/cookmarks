"""Auth dependencies. `current_user` is the gate every /api route (bar health and the
auth routes themselves) hangs off — applied centrally in `app/api/router.py`."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.db import SessionDep
from app.models.user import User
from app.services.auth import COOKIE_NAME, implicit_user, resolve_session


def current_user(request: Request, session: SessionDep) -> User:
    if settings.auth_mode == "none":
        return implicit_user(session)
    token = request.cookies.get(COOKIE_NAME)
    user = resolve_session(session, token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]

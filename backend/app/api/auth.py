from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser
from app.config import settings
from app.db import SessionDep
from app.models.user import User
from app.schemas.auth import AuthMe, LoginRequest, UserUpdate
from app.services.auth import (
    COOKIE_NAME,
    SESSION_TTL,
    create_session,
    delete_session,
    verify_dummy_password,
    verify_password,
)

router = APIRouter(tags=["auth"])


def _me(user: User) -> AuthMe:
    return AuthMe(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        auth_mode=settings.auth_mode,
        cooking_instructions=user.cooking_instructions,
    )


@router.post("/auth/login", response_model=AuthMe)
def login(body: LoginRequest, response: Response, session: SessionDep) -> AuthMe:
    """One generic failure for both an unknown username and a wrong password, so the
    response never confirms which accounts exist."""
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None:
        # Same work as a real check, so a missing account can't be spotted by timing.
        verify_dummy_password(body.password)
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    token = create_session(session, user)
    # The deployment is plain HTTP on the LAN/tailnet, so the cookie is deliberately not
    # Secure. Lax keeps it on ordinary navigation while blocking cross-site POSTs.
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return _me(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, session: SessionDep) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        delete_session(session, token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/auth/me", response_model=AuthMe)
def me(user: CurrentUser) -> AuthMe:
    return _me(user)


@router.patch("/auth/me", response_model=AuthMe)
def update_me(body: UserUpdate, user: CurrentUser, session: SessionDep) -> AuthMe:
    if "cooking_instructions" in body.model_fields_set:
        user.cooking_instructions = (
            body.cooking_instructions.strip() if body.cooking_instructions else None
        )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _me(user)


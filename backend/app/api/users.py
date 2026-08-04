import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import AdminUser
from app.db import SessionDep
from app.models.user import User
from app.schemas.auth import PasswordReset, UserCreate, UserRead
from app.services.users import UserError, create_user, delete_user, set_password

router = APIRouter(tags=["users"])

# Admin-only; the gate is applied where this router is included (app/api/router.py).


@router.get("/users", response_model=list[UserRead])
def list_users(session: SessionDep) -> list[UserRead]:
    users = session.scalars(select(User).order_by(User.created_at)).all()
    return [UserRead.model_validate(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def add_user(body: UserCreate, session: SessionDep) -> UserRead:
    try:
        user = create_user(session, body.username, body.password, body.is_admin)
    except UserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return UserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(user_id: uuid.UUID, session: SessionDep, admin: AdminUser) -> Response:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account.")
    try:
        delete_user(session, user)
    except UserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID, body: PasswordReset, session: SessionDep
) -> Response:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        set_password(session, user, body.password)
    except UserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthMe(BaseModel):
    """The signed-in user, plus the deployment's auth mode — the SPA hides all account
    chrome (login, logout, the Users tab) when the mode is "none"."""

    id: uuid.UUID
    username: str
    is_admin: bool
    auth_mode: str
    book_grid_density: Literal["sparse", "standard", "compact"] = "standard"


class UserPreferencesUpdate(BaseModel):
    book_grid_density: Literal["sparse", "standard", "compact"] = "standard"


class UserRead(BaseModel):
    """One account as it appears in the admin Users tab."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    is_admin: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class PasswordReset(BaseModel):
    password: str

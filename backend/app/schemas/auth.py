import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class AuthMe(BaseModel):
    id: uuid.UUID
    username: str
    is_admin: bool
    auth_mode: str
    user_instructions: str | None = None
    book_grid_density: Literal["sparse", "standard", "compact"] = "standard"


class UserUpdate(BaseModel):
    user_instructions: str | None = Field(default=None, max_length=4000)
    book_grid_density: Literal["sparse", "standard", "compact"] | None = None


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

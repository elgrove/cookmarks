import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthMe(BaseModel):
    id: uuid.UUID
    username: str
    is_admin: bool
    auth_mode: str
    cooking_instructions: str | None = None


class UserUpdate(BaseModel):
    cooking_instructions: str | None = Field(default=None, max_length=4000)


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

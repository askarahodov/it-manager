from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import UserRole


class UserBase(BaseModel):
    email: str = Field(..., min_length=3)
    role: UserRole = UserRole.user
    allowed_environments: Optional[list[str]] = None
    allowed_group_ids: Optional[list[int]] = None
    allowed_project_ids: Optional[list[int]] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None
    password: Optional[str] = Field(default=None, min_length=6)
    allowed_environments: Optional[list[str]] = None
    allowed_group_ids: Optional[list[int]] = None
    allowed_project_ids: Optional[list[int]] = None


class UserRead(UserBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

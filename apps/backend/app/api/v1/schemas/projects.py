from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=64)
    description: Optional[str] = None


class ProjectRead(ProjectBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


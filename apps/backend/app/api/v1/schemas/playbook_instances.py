from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaybookInstanceBase(BaseModel):
    name: str = Field(..., min_length=3)
    template_id: int
    description: Optional[str] = None
    values: dict[str, Any] = Field(default_factory=dict)
    host_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)


class PlaybookInstanceCreate(PlaybookInstanceBase):
    pass


class PlaybookInstanceUpdate(BaseModel):
    name: Optional[str] = None
    template_id: Optional[int] = None
    description: Optional[str] = None
    values: Optional[dict[str, Any]] = None
    host_ids: Optional[list[int]] = None
    group_ids: Optional[list[int]] = None


class PlaybookInstanceRead(PlaybookInstanceBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


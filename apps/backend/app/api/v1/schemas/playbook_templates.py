from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaybookTemplateBase(BaseModel):
    name: str = Field(..., min_length=3)
    description: Optional[str] = None
    vars_schema: dict[str, Any] = Field(default_factory=dict)
    vars_defaults: dict[str, Any] = Field(default_factory=dict)


class PlaybookTemplateCreate(PlaybookTemplateBase):
    pass


class PlaybookTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    vars_schema: Optional[dict[str, Any]] = None
    vars_defaults: Optional[dict[str, Any]] = None


class PlaybookTemplateRead(PlaybookTemplateBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


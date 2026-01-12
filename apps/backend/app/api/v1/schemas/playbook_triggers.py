from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaybookTriggerBase(BaseModel):
    playbook_id: int
    type: str = Field(..., description="host_created|host_tags_changed")
    enabled: bool = True
    filters: dict[str, Any] = Field(default_factory=dict)
    extra_vars: dict[str, Any] = Field(default_factory=dict)


class PlaybookTriggerCreate(PlaybookTriggerBase):
    pass


class PlaybookTriggerUpdate(BaseModel):
    playbook_id: Optional[int] = None
    type: Optional[str] = None
    enabled: Optional[bool] = None
    filters: Optional[dict[str, Any]] = None
    extra_vars: Optional[dict[str, Any]] = None


class PlaybookTriggerRead(PlaybookTriggerBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationEndpointBase(BaseModel):
    name: str = Field(..., min_length=2)
    type: str = Field(default="webhook")
    url: str = Field(..., min_length=5)
    secret: Optional[str] = None
    events: list[str] = Field(default_factory=list)
    enabled: bool = True


class NotificationEndpointCreate(NotificationEndpointBase):
    pass


class NotificationEndpointUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[list[str]] = None
    enabled: Optional[bool] = None


class NotificationEndpointRead(NotificationEndpointBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

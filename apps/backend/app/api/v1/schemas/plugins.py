from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PluginType = Literal["inventory", "secrets", "automation"]


class PluginDefinition(BaseModel):
    id: str
    type: PluginType
    name: str
    description: Optional[str] = None
    config_schema: list[dict[str, Any]] = Field(default_factory=list)


class PluginInstanceBase(BaseModel):
    name: str = Field(..., min_length=2)
    type: PluginType
    definition_id: str
    enabled: bool = True
    is_default: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class PluginInstanceCreate(PluginInstanceBase):
    pass


class PluginInstanceUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class PluginInstanceRead(PluginInstanceBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

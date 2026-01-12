from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import GroupType


class GroupBase(BaseModel):
    name: str = Field(..., min_length=2)
    type: GroupType
    description: Optional[str] = None


class GroupCreate(GroupBase):
    host_ids: List[int] = Field(default_factory=list, description="Только для static групп")
    rule: Optional[dict[str, Any]] = Field(default=None, description="Только для dynamic групп")


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    host_ids: Optional[List[int]] = None
    rule: Optional[dict[str, Any]] = None


class GroupRead(GroupBase):
    id: int
    project_id: int
    rule: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class GroupHostsUpdate(BaseModel):
    host_ids: List[int] = Field(default_factory=list)

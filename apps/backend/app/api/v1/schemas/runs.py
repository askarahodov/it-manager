from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import JobStatus


class RunCreateRequest(BaseModel):
    host_ids: list[int] = Field(default_factory=list, description="Явные хосты-цели")
    group_ids: list[int] = Field(default_factory=list, description="Группы-цели (состав будет зафиксирован)")
    extra_vars: dict[str, Any] = Field(default_factory=dict, description="Доп. переменные/оверрайд")
    dry_run: bool = Field(default=False, description="Ansible --check")


class RunRead(BaseModel):
    id: int
    project_id: int
    playbook_id: int
    triggered_by: str
    status: JobStatus
    target_snapshot: dict[str, Any]
    logs: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunClaimResponse(BaseModel):
    run: RunRead
    playbook: dict[str, Any]


class RunAppendLogRequest(BaseModel):
    chunk: str = Field(..., min_length=1)


class RunSetStatusRequest(BaseModel):
    status: JobStatus
    finished_at: Optional[datetime] = None

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApprovalRead(BaseModel):
    id: int
    project_id: int
    run_id: int
    status: str
    reason: Optional[str] = None
    requested_by: Optional[int] = None
    decided_by: Optional[int] = None
    created_at: datetime
    decided_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    reason: Optional[str] = None

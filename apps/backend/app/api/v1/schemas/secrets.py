from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SecretType(str, Enum):
    text = "text"
    password = "password"
    token = "token"
    private_key = "private_key"

class SecretScope(str, Enum):
    project = "project"
    global_ = "global"


class SecretBase(BaseModel):
    name: str = Field(..., min_length=3)
    type: SecretType
    scope: SecretScope = SecretScope.project
    description: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    rotation_interval_days: Optional[int] = Field(default=None, ge=1)
    dynamic_enabled: bool = False
    dynamic_ttl_seconds: Optional[int] = Field(default=None, ge=60)


class SecretCreate(SecretBase):
    value: str = Field(..., min_length=1)
    passphrase: Optional[str] = None


class SecretUpdate(SecretBase):
    value: Optional[str] = Field(None, min_length=1)
    passphrase: Optional[str] = None


class SecretRead(SecretBase):
    id: int
    project_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_rotated_at: Optional[datetime] = None
    next_rotated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SecretReveal(BaseModel):
    value: str


class SecretRevealInternal(BaseModel):
    """Раскрытие секрета для доверенных компонентов (воркер).

    UI не использует этот ответ.
    """

    value: str
    passphrase: Optional[str] = None


class SecretRotateRequest(BaseModel):
    value: str = Field(..., min_length=1)
    passphrase: Optional[str] = None


class SecretRotateApplyRequest(BaseModel):
    value: str = Field(..., min_length=1)
    passphrase: Optional[str] = None


class SecretLeaseRequest(BaseModel):
    ttl_seconds: Optional[int] = Field(default=None, ge=60)


class SecretLeaseRead(BaseModel):
    id: int
    secret_id: int
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    issued_at: datetime
    issued_by: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SecretLeaseIssueResponse(SecretLeaseRead):
    value: str

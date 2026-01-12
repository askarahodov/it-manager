from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import HostStatus as HostStatusEnum
from app.db.models import HostCheckMethod as HostCheckMethodEnum


def _validate_hostname(value: str) -> str:
    """Базовая валидация hostname/IP (защита от SSRF/подстановок).

    Допускаем:
    - IPv4/IPv6
    - DNS-имя/label (в т.ч. docker service name типа `ssh-demo`)
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("hostname не должен быть пустым")
    if any(ch.isspace() for ch in v):
        raise ValueError("hostname не должен содержать пробелы")
    # запрет URL/путей/параметров
    banned = ["://", "/", "\\", "?", "#", "@", "\x00"]
    if any(x in v for x in banned):
        raise ValueError("hostname должен быть хостом/IP без схемы URL и путей")
    if len(v) > 253:
        raise ValueError("hostname слишком длинный")
    return v


class HostBase(BaseModel):
    name: str = Field(..., min_length=3)
    hostname: str = Field(..., min_length=3)
    port: int = Field(22, ge=1, le=65535)
    username: str = Field("root", min_length=2)
    os_type: str = "linux"
    environment: str = "prod"
    tags: Dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    credential_id: Optional[int] = None
    check_method: HostCheckMethodEnum = HostCheckMethodEnum.tcp
    record_ssh: bool = False

    @field_validator("hostname")
    @classmethod
    def _validate_hostname_field(cls, v: str) -> str:
        return _validate_hostname(v)


class HostCreate(HostBase):
    pass


class HostUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    os_type: Optional[str] = None
    environment: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    credential_id: Optional[int] = None
    check_method: Optional[HostCheckMethodEnum] = None
    record_ssh: Optional[bool] = None

    @field_validator("hostname")
    @classmethod
    def _validate_hostname_update(cls, v: str) -> str:
        return _validate_hostname(v)


class HostStatusCheckResponse(BaseModel):
    id: int
    status: HostStatusEnum
    last_checked_at: Optional[datetime]
    health_snapshot: Optional[Dict[str, float | int | str]] = None
    health_checked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class HostRead(HostBase):
    id: int
    project_id: int
    status: HostStatusEnum = HostStatusEnum.unknown
    last_checked_at: Optional[datetime]
    last_run_id: Optional[int] = None
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime] = None
    health_snapshot: Optional[Dict[str, float | int | str]] = None
    health_checked_at: Optional[datetime] = None
    facts_snapshot: Optional[Dict[str, Any]] = None
    facts_checked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class HostHealthHistoryRead(BaseModel):
    id: int
    host_id: int
    status: HostStatusEnum
    snapshot: Optional[Dict[str, float | int | str]] = None
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HostFactsUpdate(BaseModel):
    facts: Dict[str, Any]


class SshSessionRead(BaseModel):
    id: int
    host_id: int
    actor: str
    source_ip: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    success: bool
    error: Optional[str] = None
    transcript: Optional[str] = None
    transcript_truncated: bool = False

    model_config = ConfigDict(from_attributes=True)


class HostActionRequest(BaseModel):
    action_type: str = Field(..., pattern="^(reboot|restart_service|fetch_logs|upload_file)$")
    service_name: Optional[str] = None
    log_path: Optional[str] = None
    log_lines: Optional[int] = Field(default=200, ge=1, le=5000)
    file_dest: Optional[str] = None
    file_content: Optional[str] = None
    file_mode: Optional[str] = None

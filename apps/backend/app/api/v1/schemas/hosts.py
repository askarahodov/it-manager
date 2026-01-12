from datetime import datetime
from typing import Dict, Optional

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

    @field_validator("hostname")
    @classmethod
    def _validate_hostname_update(cls, v: str) -> str:
        return _validate_hostname(v)


class HostStatusCheckResponse(BaseModel):
    id: int
    status: HostStatusEnum
    last_checked_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class HostRead(HostBase):
    id: int
    project_id: int
    status: HostStatusEnum = HostStatusEnum.unknown
    last_checked_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

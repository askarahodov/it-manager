from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SecretType(str, Enum):
    text = "text"
    password = "password"
    token = "token"
    private_key = "private_key"


class SecretBase(BaseModel):
    name: str = Field(..., min_length=3)
    type: SecretType
    scope: str = "global"
    description: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)


class SecretCreate(SecretBase):
    value: str = Field(..., min_length=1)
    passphrase: Optional[str] = None


class SecretUpdate(SecretBase):
    value: Optional[str] = Field(None, min_length=1)
    passphrase: Optional[str] = None


class SecretRead(SecretBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SecretReveal(BaseModel):
    value: str


class SecretRevealInternal(BaseModel):
    """Раскрытие секрета для доверенных компонентов (воркер).

    UI не использует этот ответ.
    """

    value: str
    passphrase: Optional[str] = None

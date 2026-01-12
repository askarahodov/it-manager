from typing import Optional

from pydantic import BaseModel, Field


class GlobalSettings(BaseModel):
    maintenance_mode: bool = False
    banner_message: Optional[str] = None
    banner_level: str = Field(default="info", pattern="^(info|warning|error)$")
    default_project_id: Optional[int] = None


class GlobalSettingsPublic(BaseModel):
    maintenance_mode: bool = False
    banner_message: Optional[str] = None
    banner_level: str = Field(default="info", pattern="^(info|warning|error)$")


class GlobalSettingsUpdate(BaseModel):
    maintenance_mode: Optional[bool] = None
    banner_message: Optional[str] = None
    banner_level: Optional[str] = Field(default=None, pattern="^(info|warning|error)$")
    default_project_id: Optional[int] = None

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlaybookSchedule(BaseModel):
    """Расписание запуска плейбука (MVP).

    Хранится в `Playbook.variables.__schedule` до внедрения полноценной модели/миграций.
    """

    enabled: bool = False
    type: Literal["interval", "cron"] = "interval"
    value: str = Field(default="300", description="interval: секунды; cron: выражение (5 полей)")
    host_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    extra_vars: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    last_run_at: Optional[str] = Field(
        default=None,
        description="Сервисное поле (UTC ISO). Заполняется воркером.",
    )


class PlaybookBase(BaseModel):
    name: str = Field(..., min_length=2)
    description: Optional[str] = None
    stored_content: Optional[str] = Field(
        default=None,
        description="YAML содержимое плейбука (вариант хранения MVP).",
    )
    repo_path: Optional[str] = Field(
        default=None,
        description="Путь к репозиторию/каталогу с плейбуком (расширение на будущее).",
    )
    inventory_scope: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    schedule: Optional[PlaybookSchedule] = None


class PlaybookCreate(PlaybookBase):
    pass


class PlaybookUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stored_content: Optional[str] = None
    repo_path: Optional[str] = None
    inventory_scope: Optional[list[dict[str, Any]]] = None
    variables: Optional[dict[str, Any]] = None
    schedule: Optional[PlaybookSchedule] = None


class PlaybookRead(PlaybookBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

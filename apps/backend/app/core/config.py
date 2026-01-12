import json
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "IT Manager API"
    # Pydantic-settings (v2) пытается парсить List из env как JSON ещё до валидации,
    # поэтому храним как строку и парсим сами (CSV или JSON-массив).
    frontend_cors_origins: str = "http://localhost:4173"
    database_url: str = "postgresql+asyncpg://postgres:password@db:5432/it_manager"
    redis_url: str = "redis://redis:6379/0"
    master_key: str = "change-me"
    secret_key: str = "change-me"
    artifacts_dir: str = "/var/ansible"
    bootstrap_admin_email: str = "admin@it.local"
    bootstrap_admin_password: str = "admin123"
    json_logs: bool = False

    @property
    def frontend_cors_origins_list(self) -> List[str]:
        raw = (self.frontend_cors_origins or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("FRONTEND_CORS_ORIGINS must be a JSON array or a comma-separated string")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

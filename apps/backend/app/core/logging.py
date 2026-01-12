from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.request_id import get_request_id


class RequestIdFilter(logging.Filter):
    """Добавляет request_id в каждую запись логов (если есть в контексте)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        rid = get_request_id()
        record.request_id = rid or "-"  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Простой JSON formatter для структурированных логов.

    Не зависит от сторонних библиотек (structlog).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(json_logs: bool = False) -> None:
    """Настройка логирования приложения.

    По умолчанию используем читаемый формат, но можно включить JSON:
    - `JSON_LOGS=1`
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s")
        )

    # Сбрасываем дефолтные handlers, чтобы не дублировать вывод в uvicorn
    root.handlers = [handler]

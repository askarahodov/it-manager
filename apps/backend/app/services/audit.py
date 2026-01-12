"""Сервис аудита.

Цель: централизованно писать события в БД, не мешая основному флоу.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_context import get_source_ip
from app.db.models import AuditEvent

logger = logging.getLogger(__name__)


async def audit_log(
    db: AsyncSession,
    *,
    project_id: int | None = None,
    actor: str,
    actor_role: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    success: bool = True,
    meta: Optional[dict[str, Any]] = None,
    source_ip: str | None = None,
) -> None:
    """Пишет событие аудита.

    Ошибки логирования не должны ломать продуктовую операцию.
    """

    try:
        event = AuditEvent(
            project_id=project_id,
            actor=actor,
            actor_role=actor_role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            success=1 if success else 0,
            meta=meta or {},
            source_ip=source_ip or get_source_ip(),
        )
        db.add(event)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:
            pass
        logger.debug("Не удалось записать audit event %s: %s", action, exc)

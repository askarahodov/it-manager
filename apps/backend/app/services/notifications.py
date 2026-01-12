from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NotificationEndpoint

logger = logging.getLogger(__name__)


async def notify_event(
    db: AsyncSession,
    *,
    project_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    query = await db.execute(
        select(NotificationEndpoint)
        .where(NotificationEndpoint.project_id == project_id)
        .where(NotificationEndpoint.enabled.is_(True))
    )
    endpoints = query.scalars().all()
    if not endpoints:
        return

    body = {
        "event": event,
        "project_id": project_id,
        "payload": payload,
        "sent_at": datetime.utcnow().isoformat(),
    }

    async with httpx.AsyncClient(timeout=8.0) as client:
        for endpoint in endpoints:
            if endpoint.events and event not in (endpoint.events or []):
                continue
            headers = {"Content-Type": "application/json"}
            if endpoint.secret:
                headers["X-Webhook-Secret"] = endpoint.secret
            try:
                await client.post(endpoint.url, json=body, headers=headers)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Notification webhook failed url=%s event=%s error=%s", endpoint.url, event, exc)

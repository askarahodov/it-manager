from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import NotificationEndpoint

logger = logging.getLogger(__name__)


def _format_message(event: str, payload: dict[str, Any]) -> str:
    return f"Event: {event}\nPayload: {payload}"


async def _send_email(to_addr: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise RuntimeError("SMTP not configured")

    def _send() -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to_addr
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_tls:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)

    await asyncio.to_thread(_send)


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
            try:
                if endpoint.type == "email":
                    to_addr = endpoint.url.replace("mailto:", "").strip()
                    if not to_addr:
                        continue
                    await _send_email(
                        to_addr=to_addr,
                        subject=f"IT Manager: {event}",
                        body=_format_message(event, payload),
                    )
                    continue

                headers = {"Content-Type": "application/json"}
                if endpoint.secret:
                    headers["X-Webhook-Secret"] = endpoint.secret
                if endpoint.type == "slack":
                    await client.post(endpoint.url, json={"text": _format_message(event, payload)}, headers=headers)
                elif endpoint.type == "telegram":
                    await client.post(endpoint.url, json={"text": _format_message(event, payload)}, headers=headers)
                else:
                    await client.post(endpoint.url, json=body, headers=headers)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Notification failed url=%s event=%s type=%s error=%s", endpoint.url, event, endpoint.type, exc)

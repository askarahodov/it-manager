import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_current_user, get_db
from app.api.v1.schemas.audit import AuditEventRead
from app.db.models import AuditEvent

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/", response_model=list[AuditEventRead])
async def list_audit(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor: Optional[str] = None,
    source_ip: Optional[str] = None,
):
    _require_admin(user)
    q = select(AuditEvent).where(AuditEvent.project_id == project_id).order_by(desc(AuditEvent.created_at)).limit(limit)
    if action:
        q = q.where(AuditEvent.action == action)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if actor:
        q = q.where(AuditEvent.actor == actor)
    if source_ip:
        q = q.where(AuditEvent.source_ip == source_ip)
    query = await db.execute(q)
    items = query.scalars().all()
    # success хранится как 1/0 (int); приводим к bool для схемы
    for it in items:
        it.success = bool(it.success)
    return items

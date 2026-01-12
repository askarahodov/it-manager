import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_current_user, get_db
from app.api.v1.schemas.notifications import (
    NotificationEmitRequest,
    NotificationEndpointCreate,
    NotificationEndpointRead,
    NotificationEndpointUpdate,
)
from app.db.models import NotificationEndpoint
from app.services.audit import audit_log
from app.services.notifications import notify_event

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/", response_model=list[NotificationEndpointRead])
async def list_endpoints(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    query = await db.execute(
        select(NotificationEndpoint)
        .where(NotificationEndpoint.project_id == project_id)
        .order_by(NotificationEndpoint.id.desc())
    )
    return query.scalars().all()


@router.post("/", response_model=NotificationEndpointRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    payload: NotificationEndpointCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    endpoint = NotificationEndpoint(**payload.model_dump(), project_id=project_id)
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    await audit_log(
        db,
        project_id=project_id,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="notification.create",
        entity_type="notification_endpoint",
        entity_id=endpoint.id,
        meta={"name": endpoint.name, "type": endpoint.type, "events": endpoint.events},
    )
    return endpoint


@router.put("/{endpoint_id}", response_model=NotificationEndpointRead)
async def update_endpoint(
    endpoint_id: int,
    payload: NotificationEndpointUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    endpoint = await db.get(NotificationEndpoint, endpoint_id)
    if not endpoint or endpoint.project_id != project_id:
        raise HTTPException(status_code=404, detail="Endpoint не найден")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(endpoint, field, value)
    await db.commit()
    await db.refresh(endpoint)
    await audit_log(
        db,
        project_id=project_id,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="notification.update",
        entity_type="notification_endpoint",
        entity_id=endpoint.id,
        meta={"name": endpoint.name, "type": endpoint.type, "events": endpoint.events},
    )
    return endpoint


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    endpoint = await db.get(NotificationEndpoint, endpoint_id)
    if not endpoint or endpoint.project_id != project_id:
        raise HTTPException(status_code=404, detail="Endpoint не найден")
    await db.delete(endpoint)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=user.get("sub"),
        actor_role=user.get("role"),
        action="notification.delete",
        entity_type="notification_endpoint",
        entity_id=endpoint_id,
        meta={"name": endpoint.name, "type": endpoint.type},
    )
    return None


@router.post("/emit", status_code=status.HTTP_204_NO_CONTENT)
async def emit_notification(
    payload: NotificationEmitRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(user)
    await notify_event(db, project_id=project_id, event=payload.event, payload=payload.payload)
    return None

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.playbook_triggers import PlaybookTriggerCreate, PlaybookTriggerRead, PlaybookTriggerUpdate
from app.core.rbac import Permission
from app.db.models import Playbook, PlaybookTrigger
from app.services.audit import audit_log

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_admin(principal) -> None:
    if getattr(principal.role, "value", str(principal.role)) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/", response_model=list[PlaybookTriggerRead])
async def list_triggers(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        select(PlaybookTrigger).where(PlaybookTrigger.project_id == project_id).order_by(PlaybookTrigger.id.desc())
    )
    return query.scalars().all()


@router.post("/", response_model=PlaybookTriggerRead, status_code=status.HTTP_201_CREATED)
async def create_trigger(
    payload: PlaybookTriggerCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    playbook = await db.get(Playbook, payload.playbook_id)
    if not playbook or playbook.project_id != project_id:
        raise HTTPException(status_code=400, detail="Плейбук не найден в текущем проекте")

    trigger = PlaybookTrigger(**payload.model_dump(), project_id=project_id, created_by=principal.id)
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="trigger.create",
        entity_type="trigger",
        entity_id=trigger.id,
        meta={"playbook_id": trigger.playbook_id, "type": trigger.type},
    )
    return trigger


@router.put("/{trigger_id}", response_model=PlaybookTriggerRead)
async def update_trigger(
    trigger_id: int,
    payload: PlaybookTriggerUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    trigger = await db.get(PlaybookTrigger, trigger_id)
    if not trigger or trigger.project_id != project_id:
        raise HTTPException(status_code=404, detail="Триггер не найден")

    updates = payload.model_dump(exclude_unset=True)
    if "playbook_id" in updates and updates["playbook_id"] is not None:
        playbook = await db.get(Playbook, int(updates["playbook_id"]))
        if not playbook or playbook.project_id != project_id:
            raise HTTPException(status_code=400, detail="Плейбук не найден в текущем проекте")

    for field, value in updates.items():
        setattr(trigger, field, value)
    await db.commit()
    await db.refresh(trigger)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="trigger.update",
        entity_type="trigger",
        entity_id=trigger.id,
        meta={"playbook_id": trigger.playbook_id, "type": trigger.type},
    )
    return trigger


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    trigger = await db.get(PlaybookTrigger, trigger_id)
    if not trigger or trigger.project_id != project_id:
        raise HTTPException(status_code=404, detail="Триггер не найден")
    await db.delete(trigger)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="trigger.delete",
        entity_type="trigger",
        entity_id=trigger_id,
        meta={"playbook_id": trigger.playbook_id, "type": trigger.type},
    )
    return None

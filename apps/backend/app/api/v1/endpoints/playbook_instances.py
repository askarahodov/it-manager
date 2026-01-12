import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.playbook_instances import (
    PlaybookInstanceCreate,
    PlaybookInstanceRead,
    PlaybookInstanceUpdate,
)
from app.core.rbac import Permission
from app.db.models import PlaybookInstance, PlaybookTemplate
from app.services.audit import audit_log

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[PlaybookInstanceRead])
async def list_instances(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        select(PlaybookInstance).where(PlaybookInstance.project_id == project_id).order_by(PlaybookInstance.name)
    )
    return query.scalars().all()


@router.post("/", response_model=PlaybookInstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: PlaybookInstanceCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    template = await db.get(PlaybookTemplate, payload.template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=400, detail="Шаблон не найден в текущем проекте")
    instance = PlaybookInstance(**payload.model_dump(), project_id=project_id, created_by=principal.id)
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_instance.create",
        entity_type="playbook_instance",
        entity_id=instance.id,
        meta={"name": instance.name, "template_id": instance.template_id},
    )
    return instance


@router.get("/{instance_id}", response_model=PlaybookInstanceRead)
async def get_instance(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    instance = await db.get(PlaybookInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Инстанс не найден")
    return instance


@router.put("/{instance_id}", response_model=PlaybookInstanceRead)
async def update_instance(
    instance_id: int,
    payload: PlaybookInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    instance = await db.get(PlaybookInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Инстанс не найден")
    updates = payload.model_dump(exclude_unset=True)
    if "template_id" in updates and updates["template_id"] is not None:
        template = await db.get(PlaybookTemplate, int(updates["template_id"]))
        if not template or template.project_id != project_id:
            raise HTTPException(status_code=400, detail="Шаблон не найден в текущем проекте")
    for field, value in updates.items():
        setattr(instance, field, value)
    await db.commit()
    await db.refresh(instance)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_instance.update",
        entity_type="playbook_instance",
        entity_id=instance.id,
        meta={"name": instance.name, "template_id": instance.template_id},
    )
    return instance


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    instance = await db.get(PlaybookInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Инстанс не найден")
    await db.delete(instance)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_instance.delete",
        entity_type="playbook_instance",
        entity_id=instance.id,
        meta={"name": instance.name, "template_id": instance.template_id},
    )
    return None


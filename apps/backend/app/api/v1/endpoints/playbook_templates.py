import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.playbook_templates import (
    PlaybookTemplateCreate,
    PlaybookTemplateRead,
    PlaybookTemplateUpdate,
)
from app.core.rbac import Permission
from app.db.models import PlaybookTemplate
from app.services.audit import audit_log

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[PlaybookTemplateRead])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        select(PlaybookTemplate).where(PlaybookTemplate.project_id == project_id).order_by(PlaybookTemplate.name)
    )
    return query.scalars().all()


@router.post("/", response_model=PlaybookTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: PlaybookTemplateCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    template = PlaybookTemplate(**payload.model_dump(), project_id=project_id, created_by=principal.id)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_template.create",
        entity_type="playbook_template",
        entity_id=template.id,
        meta={"name": template.name},
    )
    return template


@router.get("/{template_id}", response_model=PlaybookTemplateRead)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    template = await db.get(PlaybookTemplate, template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return template


@router.put("/{template_id}", response_model=PlaybookTemplateRead)
async def update_template(
    template_id: int,
    payload: PlaybookTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    template = await db.get(PlaybookTemplate, template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_template.update",
        entity_type="playbook_template",
        entity_id=template.id,
        meta={"name": template.name},
    )
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    template = await db.get(PlaybookTemplate, template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    await db.delete(template)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook_template.delete",
        entity_type="playbook_template",
        entity_id=template.id,
        meta={"name": template.name},
    )
    return None


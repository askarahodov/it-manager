from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.plugins import PluginDefinition, PluginInstanceCreate, PluginInstanceRead, PluginInstanceUpdate
from app.core.rbac import Permission
from app.db.models import PluginInstance
from app.services.audit import audit_log
from app.services.plugins import list_definitions, validate_definition

router = APIRouter()


def _require_admin(principal) -> None:
    if getattr(principal.role, "value", str(principal.role)) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


@router.get("/definitions", response_model=list[PluginDefinition])
async def get_definitions(
    principal=Depends(require_permission(Permission.projects_read)),
):
    _require_admin(principal)
    return list_definitions()


@router.get("/", response_model=list[PluginInstanceRead])
async def list_instances(
    db: AsyncSession = Depends(get_db),
    project_id: int = Depends(get_current_project_id),
    principal=Depends(require_permission(Permission.projects_read)),
):
    _require_admin(principal)
    rows = await db.execute(
        select(PluginInstance)
        .where(PluginInstance.project_id == project_id)
        .order_by(PluginInstance.id.desc())
    )
    return rows.scalars().all()


@router.post("/", response_model=PluginInstanceRead, status_code=status.HTTP_201_CREATED)
async def create_instance(
    payload: PluginInstanceCreate,
    db: AsyncSession = Depends(get_db),
    project_id: int = Depends(get_current_project_id),
    principal=Depends(require_permission(Permission.projects_write)),
):
    _require_admin(principal)
    try:
        validate_definition(payload.definition_id, payload.type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.is_default and payload.enabled is False:
        raise HTTPException(status_code=400, detail="Default plugin должен быть enabled")

    if payload.is_default:
        await db.execute(
            update(PluginInstance)
            .where(PluginInstance.project_id == project_id, PluginInstance.type == payload.type)
            .values(is_default=False)
        )

    instance = PluginInstance(**payload.model_dump(), project_id=project_id)
    db.add(instance)
    await db.commit()
    await db.refresh(instance)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="plugin_instance.create",
        entity_type="plugin_instance",
        entity_id=instance.id,
        meta={"name": instance.name, "type": instance.type.value, "definition_id": instance.definition_id},
    )
    return instance


@router.put("/{instance_id}", response_model=PluginInstanceRead)
async def update_instance(
    instance_id: int,
    payload: PluginInstanceUpdate,
    db: AsyncSession = Depends(get_db),
    project_id: int = Depends(get_current_project_id),
    principal=Depends(require_permission(Permission.projects_write)),
):
    _require_admin(principal)
    instance = await db.get(PluginInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Plugin instance не найден")

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_default") and updates.get("enabled") is False:
        raise HTTPException(status_code=400, detail="Default plugin должен быть enabled")

    if updates.get("is_default"):
        await db.execute(
            update(PluginInstance)
            .where(PluginInstance.project_id == project_id, PluginInstance.type == instance.type)
            .values(is_default=False)
        )

    for field, value in updates.items():
        setattr(instance, field, value)
    await db.commit()
    await db.refresh(instance)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="plugin_instance.update",
        entity_type="plugin_instance",
        entity_id=instance.id,
        meta={"name": instance.name, "type": instance.type.value, "definition_id": instance.definition_id},
    )
    return instance


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: int,
    db: AsyncSession = Depends(get_db),
    project_id: int = Depends(get_current_project_id),
    principal=Depends(require_permission(Permission.projects_write)),
):
    _require_admin(principal)
    instance = await db.get(PluginInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Plugin instance не найден")
    await db.delete(instance)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="plugin_instance.delete",
        entity_type="plugin_instance",
        entity_id=instance_id,
        meta={"name": instance.name, "type": instance.type.value, "definition_id": instance.definition_id},
    )
    return None

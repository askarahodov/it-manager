import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.groups import GroupCreate, GroupHostsUpdate, GroupRead, GroupUpdate
from app.api.v1.schemas.hosts import HostRead
from app.core.rbac import Permission
from app.db.models import DynamicGroupHostCache, GroupHost, GroupType, Host, HostGroup
from app.services.access import apply_group_scope, apply_host_scope
from app.services.audit import audit_log
from app.services.group_rules import build_host_filter

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=list[GroupRead])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(select(HostGroup).where(HostGroup.project_id == project_id).order_by(HostGroup.name), principal)
    )
    return query.scalars().all()


@router.post("/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):

    if payload.type == GroupType.static and payload.rule:
        raise HTTPException(status_code=400, detail="Для static группы правило не используется")
    if payload.type == GroupType.dynamic and payload.host_ids:
        raise HTTPException(status_code=400, detail="Для dynamic группы состав задаётся правилом")

    group = HostGroup(
        name=payload.name,
        type=payload.type,
        description=payload.description,
        rule=payload.rule,
        project_id=project_id,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.create",
        entity_type="group",
        entity_id=group.id,
        meta={"name": group.name, "type": group.type},
    )

    if payload.type == GroupType.static and payload.host_ids:
        await _set_static_group_hosts(db, group.id, payload.host_ids, project_id=project_id)

    if payload.type == GroupType.dynamic:
        await recompute_dynamic_group(group.id, db, principal, project_id=project_id)
        await db.refresh(group)

    return group


@router.get("/{group_id}", response_model=GroupRead)
async def get_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    return group


@router.put("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: int,
    payload: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    data = payload.model_dump(exclude_unset=True)
    if group.type == GroupType.static and "rule" in data and data["rule"] is not None:
        raise HTTPException(status_code=400, detail="Для static группы правило не используется")
    if group.type == GroupType.dynamic and "host_ids" in data and data["host_ids"] is not None:
        raise HTTPException(status_code=400, detail="Для dynamic группы состав задаётся правилом")

    for field in ("name", "description", "rule"):
        if field in data:
            setattr(group, field, data[field])

    await db.commit()
    await db.refresh(group)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.update",
        entity_type="group",
        entity_id=group.id,
        meta={"name": group.name, "type": group.type},
    )

    if group.type == GroupType.static and data.get("host_ids") is not None:
        await _set_static_group_hosts(db, group.id, data["host_ids"], project_id=project_id)
        await db.refresh(group)

    if group.type == GroupType.dynamic and "rule" in data:
        await recompute_dynamic_group(group.id, db, principal, project_id=project_id)
        await db.refresh(group)

    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    await db.delete(group)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.delete",
        entity_type="group",
        entity_id=group_id,
        meta={"name": group.name, "type": group.type},
    )
    return None


@router.get("/{group_id}/hosts", response_model=list[HostRead])
async def list_group_hosts(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    if group.type == GroupType.static:
        query = await db.execute(
            apply_host_scope(
                select(Host)
            .join(GroupHost, GroupHost.host_id == Host.id)
            .where(GroupHost.group_id == group_id)
            .where(Host.project_id == project_id)
            .order_by(Host.name),
                principal,
            )
        )
        return query.scalars().all()

    # dynamic: используем кэш; если кэша нет — считаем "на лету"
    cached = await db.execute(
        apply_host_scope(
            select(Host)
            .join(DynamicGroupHostCache, DynamicGroupHostCache.host_id == Host.id)
            .where(DynamicGroupHostCache.group_id == group_id)
            .where(Host.project_id == project_id)
            .order_by(Host.name),
            principal,
        )
    )
    hosts = cached.scalars().all()
    if hosts:
        return hosts

    expr = build_host_filter(group.rule)
    query = await db.execute(
        apply_host_scope(select(Host).where(Host.project_id == project_id).where(expr).order_by(Host.name), principal)
    )
    return query.scalars().all()


@router.put("/{group_id}/hosts", status_code=status.HTTP_204_NO_CONTENT)
async def set_group_hosts(
    group_id: int,
    payload: GroupHostsUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if group.type != GroupType.static:
        raise HTTPException(status_code=400, detail="Состав можно задавать только для static групп")
    await _set_static_group_hosts(db, group_id, payload.host_ids, project_id=project_id)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.set_hosts",
        entity_type="group",
        entity_id=group_id,
        meta={"host_ids": payload.host_ids},
    )
    return None


async def _set_static_group_hosts(db: AsyncSession, group_id: int, host_ids: list[int], *, project_id: int) -> None:
    # чистим и записываем заново (простая и надёжная стратегия для MVP)
    await db.execute(delete(GroupHost).where(GroupHost.group_id == group_id))
    if host_ids:
        query = await db.execute(select(Host.id).where(Host.project_id == project_id).where(Host.id.in_(host_ids)))
        existing_ids = {row[0] for row in query.all()}
        for host_id in host_ids:
            if host_id in existing_ids:
                db.add(GroupHost(group_id=group_id, host_id=host_id))
    await db.commit()


@router.post("/recompute-dynamic", status_code=status.HTTP_204_NO_CONTENT)
async def recompute_all_dynamic_groups(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(
        apply_group_scope(
            select(HostGroup.id)
            .where(HostGroup.project_id == project_id)
            .where(HostGroup.type == GroupType.dynamic),
            principal,
        )
    )
    ids = [row[0] for row in query.all()]
    for group_id in ids:
        await recompute_dynamic_group(group_id, db, principal, project_id=project_id)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.recompute_all_dynamic",
        entity_type="group",
        meta={"count": len(ids)},
    )
    return None


@router.post("/{group_id}/recompute-dynamic", status_code=status.HTTP_204_NO_CONTENT)
async def recompute_dynamic_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):

    query = await db.execute(
        apply_group_scope(
            select(HostGroup).where(HostGroup.id == group_id).where(HostGroup.project_id == project_id), principal
        )
    )
    group = query.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    if group.type != GroupType.dynamic:
        raise HTTPException(status_code=400, detail="Пересчёт доступен только для dynamic групп")

    expr = build_host_filter(group.rule)
    query = await db.execute(select(Host.id).where(Host.project_id == project_id).where(expr))
    host_ids = [row[0] for row in query.all()]

    await db.execute(delete(DynamicGroupHostCache).where(DynamicGroupHostCache.group_id == group_id))
    now = datetime.utcnow()
    for host_id in host_ids:
        db.add(DynamicGroupHostCache(group_id=group_id, host_id=host_id, computed_at=now))
    await db.commit()

    logger.info("Dynamic group recomputed group_id=%s hosts=%s", group_id, len(host_ids))
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="group.recompute_dynamic",
        entity_type="group",
        entity_id=group_id,
        meta={"hosts": len(host_ids)},
    )
    return None

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.playbook_instances import (
    PlaybookInstanceCreate,
    PlaybookInstanceRead,
    PlaybookInstanceRunRequest,
    PlaybookInstanceUpdate,
)
from app.core.rbac import Permission
from app.db.models import GroupType, Host, HostGroup, JobRun, JobStatus, Playbook, PlaybookInstance, PlaybookTemplate
from app.db.models import ApprovalRequest, ApprovalStatus
from app.services.audit import audit_log
from app.services.notifications import notify_event
from app.services.access import apply_group_scope, apply_host_scope

router = APIRouter()
logger = logging.getLogger(__name__)

async def _resolve_group_hosts(db: AsyncSession, group: HostGroup, principal) -> list[Host]:
    from app.db.models import DynamicGroupHostCache, GroupHost  # локальный импорт

    if group.type == GroupType.static:
        query = await db.execute(
            apply_host_scope(
                select(Host)
                .join(GroupHost, GroupHost.host_id == Host.id)
                .where(GroupHost.group_id == group.id)
                .where(Host.project_id == group.project_id)
                .order_by(Host.name),
                principal,
            )
        )
        return query.scalars().all()

    cached = await db.execute(
        apply_host_scope(
            select(Host)
            .join(DynamicGroupHostCache, DynamicGroupHostCache.host_id == Host.id)
            .where(DynamicGroupHostCache.group_id == group.id)
            .where(Host.project_id == group.project_id)
            .order_by(Host.name),
            principal,
        )
    )
    hosts = cached.scalars().all()
    if hosts:
        return hosts

    from app.services.group_rules import build_host_filter

    expr = build_host_filter(group.rule)
    query = await db.execute(
        apply_host_scope(select(Host).where(Host.project_id == group.project_id).where(expr).order_by(Host.name), principal)
    )
    return query.scalars().all()

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


@router.post("/{instance_id}/run", response_model=dict, status_code=status.HTTP_201_CREATED)
async def run_instance(
    instance_id: int,
    payload: PlaybookInstanceRunRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_run)),
    project_id: int = Depends(get_current_project_id),
):
    instance = await db.get(PlaybookInstance, instance_id)
    if not instance or instance.project_id != project_id:
        raise HTTPException(status_code=404, detail="Инстанс не найден")

    template = await db.get(PlaybookTemplate, instance.template_id)
    if not template or template.project_id != project_id:
        raise HTTPException(status_code=400, detail="Шаблон не найден в текущем проекте")

    playbook = await db.get(Playbook, payload.playbook_id)
    if not playbook or playbook.project_id != project_id:
        raise HTTPException(status_code=400, detail="Плейбук не найден в текущем проекте")

    target_hosts: dict[int, Host] = {}
    if instance.host_ids:
        query = await db.execute(
            apply_host_scope(
                select(Host).where(Host.project_id == project_id).where(Host.id.in_(instance.host_ids)),
                principal,
            )
        )
        for host in query.scalars().all():
            target_hosts[host.id] = host

    if instance.group_ids:
        query = await db.execute(
            apply_group_scope(
                select(HostGroup)
                .where(HostGroup.project_id == project_id)
                .where(HostGroup.id.in_(instance.group_ids)),
                principal,
            )
        )
        groups = query.scalars().all()
        for group in groups:
            for host in await _resolve_group_hosts(db, group, principal):
                target_hosts[host.id] = host

    snapshot_hosts = [
        {
            "id": host.id,
            "name": host.name,
            "hostname": host.hostname,
            "port": host.port,
            "username": host.username,
            "credential_id": host.credential_id,
        }
        for host in target_hosts.values()
    ]

    defaults_vars = template.vars_defaults or {}
    merged_vars = {}
    merged_vars.update(defaults_vars)
    merged_vars.update(instance.values or {})
    merged_vars.update(payload.extra_vars or {})

    requires_approval = any(h.environment == "prod" for h in target_hosts.values())
    run = JobRun(
        project_id=project_id,
        playbook_id=payload.playbook_id,
        triggered_by=principal.email or "user",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": instance.group_ids,
            "host_ids": instance.host_ids,
            "extra_vars": merged_vars,
            "dry_run": payload.dry_run,
            "instance_id": instance.id,
            "template_id": instance.template_id,
            "repo_commit": playbook.repo_last_commit,
            "params_before": defaults_vars,
            "params_after": merged_vars,
        },
        logs="",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    from app.services.queue import enqueue_run

    if requires_approval:
        approval = ApprovalRequest(
            project_id=project_id,
            run_id=run.id,
            requested_by=principal.id,
            status=ApprovalStatus.pending,
        )
        db.add(approval)
        run.target_snapshot["approval_status"] = "pending"
        await db.commit()
        await db.refresh(approval)
        run.target_snapshot["approval_id"] = approval.id
        await db.commit()
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="run.create_from_instance_requires_approval",
            entity_type="run",
            entity_id=run.id,
            meta={"instance_id": instance.id, "playbook_id": payload.playbook_id, "targets": len(snapshot_hosts), "approval_id": approval.id},
        )
        await notify_event(
            db,
            project_id=project_id,
            event="approval.requested",
            payload={"approval_id": approval.id, "run_id": run.id, "instance_id": instance.id},
        )
    else:
        await enqueue_run(run.id, project_id=project_id)
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="run.create_from_instance",
            entity_type="run",
            entity_id=run.id,
            meta={"instance_id": instance.id, "playbook_id": payload.playbook_id, "targets": len(snapshot_hosts)},
        )
    return {"run_id": run.id}

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.playbooks import PlaybookCreate, PlaybookRead, PlaybookSchedule, PlaybookUpdate, PlaybookWebhookRead
from app.api.v1.schemas.runs import RunCreateRequest, RunRead
from app.core.rbac import Permission
from app.db.models import GroupType, Host, HostGroup, JobRun, JobStatus, Playbook
from app.db.models import ApprovalRequest, ApprovalStatus
from app.services.access import apply_group_scope, apply_host_scope
from app.services.audit import audit_log
from app.services.queue import enqueue_run

logger = logging.getLogger(__name__)
router = APIRouter()

def _require_admin(principal) -> None:
    if getattr(principal.role, "value", str(principal.role)) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Требуются права admin")


def _webhook_path(playbook_id: int, token: str) -> str:
    return f"/api/v1/playbooks/{playbook_id}/webhook?token={token}"


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


async def _resolve_group_hosts_no_scope(db: AsyncSession, group: HostGroup) -> list[Host]:
    from app.db.models import DynamicGroupHostCache, GroupHost  # локальный импорт

    if group.type == GroupType.static:
        query = await db.execute(
            select(Host)
            .join(GroupHost, GroupHost.host_id == Host.id)
            .where(GroupHost.group_id == group.id)
            .where(Host.project_id == group.project_id)
            .order_by(Host.name)
        )
        return query.scalars().all()

    cached = await db.execute(
        select(Host)
        .join(DynamicGroupHostCache, DynamicGroupHostCache.host_id == Host.id)
        .where(DynamicGroupHostCache.group_id == group.id)
        .where(Host.project_id == group.project_id)
        .order_by(Host.name)
    )
    hosts = cached.scalars().all()
    if hosts:
        return hosts

    from app.services.group_rules import build_host_filter

    expr = build_host_filter(group.rule)
    query = await db.execute(
        select(Host).where(Host.project_id == group.project_id).where(expr).order_by(Host.name)
    )
    return query.scalars().all()

@router.get("/", response_model=list[PlaybookRead])
async def list_playbooks(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    query = await db.execute(select(Playbook).where(Playbook.project_id == project_id).order_by(Playbook.name))
    playbooks = query.scalars().all()
    for pb in playbooks:
        pb.schedule = _extract_schedule(pb.variables)
    return playbooks


@router.post("/", response_model=PlaybookRead, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    payload: PlaybookCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    data = payload.model_dump()
    schedule = data.pop("schedule", None)
    variables = data.get("variables") or {}
    if schedule:
        variables = dict(variables)
        variables["__schedule"] = schedule
        data["variables"] = variables
    playbook = Playbook(**data, created_by=None, project_id=project_id)
    db.add(playbook)
    await db.commit()
    await db.refresh(playbook)
    playbook.schedule = _extract_schedule(playbook.variables)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook.create",
        entity_type="playbook",
        entity_id=playbook.id,
        meta={"name": playbook.name},
    )
    return playbook


@router.get("/{playbook_id}", response_model=PlaybookRead)
async def get_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    playbook.schedule = _extract_schedule(playbook.variables)
    return playbook


@router.get("/{playbook_id}/webhook-token", response_model=PlaybookWebhookRead)
async def get_webhook_token(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    playbook = await db.get(Playbook, playbook_id)
    if not playbook or playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if not playbook.webhook_token:
        raise HTTPException(status_code=404, detail="Webhook token не задан")
    return PlaybookWebhookRead(token=playbook.webhook_token, url_path=_webhook_path(playbook.id, playbook.webhook_token))


@router.post("/{playbook_id}/webhook-token", response_model=PlaybookWebhookRead)
async def rotate_webhook_token(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    _require_admin(principal)
    playbook = await db.get(Playbook, playbook_id)
    if not playbook or playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    playbook.webhook_token = secrets.token_urlsafe(24)
    await db.commit()
    return PlaybookWebhookRead(token=playbook.webhook_token, url_path=_webhook_path(playbook.id, playbook.webhook_token))


@router.post("/{playbook_id}/webhook", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def run_playbook_webhook(
    playbook_id: int,
    payload: RunCreateRequest,
    token: str | None = Query(default=None),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
    db: AsyncSession = Depends(get_db),
):
    provided_token = x_webhook_token or token
    if not provided_token:
        raise HTTPException(status_code=403, detail="Webhook token required")

    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if not playbook.webhook_token or playbook.webhook_token != provided_token:
        raise HTTPException(status_code=403, detail="Неверный webhook token")

    target_hosts: dict[int, Host] = {}
    if payload.host_ids:
        query = await db.execute(
            select(Host).where(Host.project_id == playbook.project_id).where(Host.id.in_(payload.host_ids))
        )
        for host in query.scalars().all():
            target_hosts[host.id] = host

    if payload.group_ids:
        query = await db.execute(
            select(HostGroup)
            .where(HostGroup.project_id == playbook.project_id)
            .where(HostGroup.id.in_(payload.group_ids))
        )
        groups = query.scalars().all()
        for group in groups:
            for host in await _resolve_group_hosts_no_scope(db, group):
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

    requires_approval = any(h.environment == "prod" for h in target_hosts.values())
    run = JobRun(
        project_id=playbook.project_id,
        playbook_id=playbook_id,
        triggered_by="webhook",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": payload.group_ids,
            "host_ids": payload.host_ids,
            "extra_vars": payload.extra_vars,
            "dry_run": payload.dry_run,
            "params_before": {},
            "params_after": payload.extra_vars or {},
        },
        logs="",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if requires_approval:
        approval = ApprovalRequest(
            project_id=playbook.project_id,
            run_id=run.id,
            requested_by=None,
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
            project_id=playbook.project_id,
            actor="webhook",
            actor_role="webhook",
            action="run.create_webhook_requires_approval",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook_id, "targets": len(snapshot_hosts), "approval_id": approval.id},
        )
    else:
        await enqueue_run(run.id, project_id=playbook.project_id)
        await audit_log(
            db,
            project_id=playbook.project_id,
            actor="webhook",
            actor_role="webhook",
            action="run.create_webhook",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook_id, "targets": len(snapshot_hosts)},
        )
    return run


@router.post("/{playbook_id}/run", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def run_playbook(
    playbook_id: int,
    payload: RunCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_run)),
    project_id: int = Depends(get_current_project_id),
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")

    target_hosts: dict[int, Host] = {}

    if payload.host_ids:
        query = await db.execute(
            apply_host_scope(
                select(Host).where(Host.project_id == project_id).where(Host.id.in_(payload.host_ids)), principal
            )
        )
        for host in query.scalars().all():
            target_hosts[host.id] = host

    if payload.group_ids:
        query = await db.execute(
            apply_group_scope(
                select(HostGroup)
                .where(HostGroup.project_id == project_id)
                .where(HostGroup.id.in_(payload.group_ids)),
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

    requires_approval = any(h.environment == "prod" for h in target_hosts.values())
    run = JobRun(
        project_id=project_id,
        playbook_id=playbook_id,
        triggered_by=principal.email or "user",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": payload.group_ids,
            "host_ids": payload.host_ids,
            "extra_vars": payload.extra_vars,
            "dry_run": payload.dry_run,
            "params_before": {},
            "params_after": payload.extra_vars or {},
        },
        logs="",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

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
            action="run.create_requires_approval",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook_id, "targets": len(snapshot_hosts), "approval_id": approval.id},
        )
    else:
        await enqueue_run(run.id, project_id=project_id)
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="run.create",
            entity_type="run",
            entity_id=run.id,
            meta={"playbook_id": playbook_id, "targets": len(snapshot_hosts)},
        )
    return run


@router.put("/{playbook_id}", response_model=PlaybookRead)
async def update_playbook(
    playbook_id: int,
    payload: PlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")

    updates = payload.model_dump(exclude_unset=True)
    schedule = updates.pop("schedule", None)
    if "variables" in updates and updates["variables"] is not None:
        playbook.variables = updates.pop("variables")

    for field, value in updates.items():
        setattr(playbook, field, value)

    if schedule is not None:
        variables = dict(playbook.variables or {})
        if schedule:
            variables["__schedule"] = schedule
        else:
            variables.pop("__schedule", None)
        playbook.variables = variables

    await db.commit()
    await db.refresh(playbook)
    playbook.schedule = _extract_schedule(playbook.variables)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook.update",
        entity_type="playbook",
        entity_id=playbook.id,
        meta={"name": playbook.name, "schedule_enabled": bool(playbook.schedule and playbook.schedule.enabled)},
    )
    return playbook


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_edit)),
    project_id: int = Depends(get_current_project_id),
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    await db.delete(playbook)
    await db.commit()
    logger.info("Playbook deleted playbook_id=%s", playbook_id)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="playbook.delete",
        entity_type="playbook",
        entity_id=playbook_id,
        meta={"name": playbook.name},
    )
    return None


@router.get("/{playbook_id}/schedule", response_model=PlaybookSchedule)
async def get_playbook_schedule(
    playbook_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_read)),
    project_id: int = Depends(get_current_project_id),
):
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    if playbook.project_id != project_id:
        raise HTTPException(status_code=404, detail="Плейбук не найден")
    return _extract_schedule(playbook.variables) or PlaybookSchedule()


def _extract_schedule(variables: dict | None) -> PlaybookSchedule | None:
    if not variables or not isinstance(variables, dict):
        return None
    raw = variables.get("__schedule")
    if not isinstance(raw, dict):
        return None
    try:
        return PlaybookSchedule(**raw)
    except Exception:
        return None

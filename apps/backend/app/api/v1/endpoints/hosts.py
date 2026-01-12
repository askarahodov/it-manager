import asyncio
import logging
import subprocess
from datetime import datetime
import json
from typing import Optional

import asyncssh
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_project_id, get_db, require_permission
from app.api.v1.schemas.hosts import HostActionRequest, HostCreate, HostFactsUpdate, HostHealthHistoryRead, HostRead, HostStatusCheckResponse, HostUpdate, SshSessionRead
from app.api.v1.schemas.runs import RunRead
from app.core.rbac import Permission, has_permission
from app.db.models import ApprovalRequest, ApprovalStatus, Host, HostCheckMethod, HostHealthCheck, HostStatus, JobRun, JobStatus, Playbook, Secret, SecretType, SshSession, User
from app.services.access import apply_host_scope, host_access_clause
from app.services.audit import audit_log
from app.services.encryption import decrypt_value
from app.services.projects import ProjectAccessDenied, ProjectNotFound, resolve_current_project_id
from app.services.triggers import dispatch_host_triggers
from app.services.queue import enqueue_run
from app.services.notifications import notify_event

router = APIRouter()
logger = logging.getLogger(__name__)

FACTS_PLAYBOOK_NAME = "_system_facts"
FACTS_PLAYBOOK_CONTENT = """---
- name: collect facts
  hosts: all
  gather_facts: true
  tasks:
    - name: facts collected
      debug:
        msg: "facts ok"
"""

REMOTE_ACTIONS_PLAYBOOK_NAME = "_remote_actions"
REMOTE_ACTIONS_PLAYBOOK_CONTENT = """---
- name: remote actions
  hosts: all
  gather_facts: false
  vars:
    action_type: "{{ action_type }}"
  tasks:
    - name: reboot host
      reboot:
        reboot_timeout: 600
      when: action_type == "reboot"
    - name: restart service
      service:
        name: "{{ service_name }}"
        state: restarted
      when: action_type == "restart_service"
    - name: upload file
      copy:
        dest: "{{ file_dest }}"
        content: "{{ file_content }}"
        mode: "{{ file_mode | default('0644') }}"
      when: action_type == "upload_file"
    - name: fetch logs
      shell: "tail -n {{ log_lines | default(200) }} {{ log_path }}"
      register: log_output
      when: action_type == "fetch_logs"
    - name: print logs
      debug:
        var: log_output.stdout
      when: action_type == "fetch_logs"
"""


async def _probe_ping(host: Host) -> HostStatus:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping",
            "-c",
            "1",
            "-W",
            "1",
            host.hostname,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        return HostStatus.online if rc == 0 else HostStatus.offline
    except FileNotFoundError:
        logger.warning("ping не установлен в контейнере backend; fallback на tcp")
        return await _probe_tcp(host)
    except Exception:
        return HostStatus.offline


async def _probe_tcp(host: Host) -> HostStatus:
    try:
        reader, writer = await asyncio.open_connection(host.hostname, host.port)
        writer.close()
        await writer.wait_closed()
        return HostStatus.online
    except asyncio.TimeoutError:
        return HostStatus.offline
    except Exception:
        return HostStatus.offline


def _get_ssh_credentials(host: Host) -> tuple[Optional[str], Optional[str], Optional[str]]:
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None

    if not host.credential:
        return password, private_key, passphrase

    decrypted = decrypt_value(host.credential.encrypted_value)
    if host.credential.type == SecretType.password:
        password = decrypted
    elif host.credential.type == SecretType.private_key:
        private_key = decrypted
        if host.credential.encrypted_passphrase:
            passphrase = decrypt_value(host.credential.encrypted_passphrase)
    return password, private_key, passphrase


def _parse_health_snapshot(output: str) -> dict[str, float | int]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    snapshot: dict[str, float | int] = {}
    if not lines:
        return snapshot
    try:
        uptime_parts = lines[0].split()
        snapshot["uptime_seconds"] = float(uptime_parts[0])
    except Exception:
        pass
    if len(lines) > 1:
        try:
            load_parts = lines[1].split()
            snapshot["load1"] = float(load_parts[0])
            snapshot["load5"] = float(load_parts[1])
            snapshot["load15"] = float(load_parts[2])
        except Exception:
            pass
    mem_total = None
    mem_available = None
    for line in lines:
        if line.startswith("MemTotal:"):
            mem_total = int(line.split()[1])
        if line.startswith("MemAvailable:"):
            mem_available = int(line.split()[1])
    if mem_total is not None:
        snapshot["mem_total_kb"] = mem_total
        if mem_available is not None:
            snapshot["mem_used_kb"] = mem_total - mem_available
    df_line = None
    for line in lines:
        parts = line.split()
        if len(parts) >= 6 and parts[-1] == "/":
            df_line = line
            break
    if df_line:
        parts = df_line.split()
        snapshot["disk_total_kb"] = int(parts[1])
        snapshot["disk_used_kb"] = int(parts[2])
        percent = parts[4].rstrip("%")
        if percent.isdigit():
            snapshot["disk_used_percent"] = int(percent)
    return snapshot


async def _probe_ssh_health(host: Host) -> tuple[HostStatus, Optional[dict[str, float | int]]]:
    """Проверка SSH и сбор метрик (uptime/load/mem/disk)."""
    try:
        password, private_key, passphrase = _get_ssh_credentials(host)
    except Exception:
        return HostStatus.offline, None

    try:
        conn = await asyncssh.connect(
            host.hostname,
            port=host.port,
            username=host.username,
            password=password,
            client_keys=[private_key] if private_key else None,
            passphrase=passphrase,
            known_hosts=None,
            server_host_key_algs=["ssh-ed25519", "ssh-rsa"],
        )
    except Exception:
        return HostStatus.offline, None

    try:
        result = await conn.run(
            "cat /proc/uptime; cat /proc/loadavg; cat /proc/meminfo; df -kP /",
            check=False,
        )
        conn.close()
        await conn.wait_closed()
    except Exception:
        conn.close()
        await conn.wait_closed()
        return HostStatus.offline, None

    if result.exit_status != 0:
        return HostStatus.online, None
    return HostStatus.online, _parse_health_snapshot(result.stdout or "")


@router.get("/", response_model=list[HostRead])
async def list_hosts(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
    search: Optional[str] = Query(default=None, description="Поиск по name/hostname (ILIKE)"),
    status_filter: Optional[HostStatus] = Query(default=None, alias="status", description="Фильтр по статусу"),
    environment: Optional[str] = Query(default=None, description="Фильтр по environment"),
    os_type: Optional[str] = Query(default=None, description="Фильтр по os_type"),
    tag_key: Optional[str] = Query(default=None, description="Фильтр по tags.<key>"),
    tag_value: Optional[str] = Query(default=None, description="Значение для tag_key"),
    sort_by: str = Query(default="name", description="Поле сортировки: name|hostname|status|environment|os_type|id"),
    sort_dir: str = Query(default="asc", description="asc|desc"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Host)
    stmt = stmt.where(Host.project_id == project_id)
    stmt = apply_host_scope(stmt, principal)

    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(or_(Host.name.ilike(q), Host.hostname.ilike(q)))
    if status_filter:
        stmt = stmt.where(Host.status == status_filter)
    if environment:
        stmt = stmt.where(Host.environment == environment)
    if os_type:
        stmt = stmt.where(Host.os_type == os_type)
    if tag_key and tag_value is not None:
        # JSONB tags: {"env":"prod"} => tags->>'env' = 'prod'
        stmt = stmt.where(Host.tags[tag_key].astext == tag_value)

    sort_map = {
        "id": Host.id,
        "name": Host.name,
        "hostname": Host.hostname,
        "status": Host.status,
        "environment": Host.environment,
        "os_type": Host.os_type,
    }
    sort_col = sort_map.get(sort_by, Host.name)
    order_fn = desc if sort_dir.lower() == "desc" else asc
    stmt = stmt.order_by(order_fn(sort_col)).limit(limit).offset(offset)

    query = await db.execute(stmt)
    hosts = query.scalars().all()
    return hosts


@router.post("/", response_model=HostRead, status_code=status.HTTP_201_CREATED)
async def create_host(
    payload: HostCreate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    if payload.credential_id:
        secret = await db.get(Secret, int(payload.credential_id))
        if not secret or (secret.project_id is not None and secret.project_id != project_id):
            raise HTTPException(status_code=400, detail="Credential должен быть из текущего проекта или global")

    new_host = Host(**payload.model_dump(), project_id=project_id)
    db.add(new_host)
    await db.commit()
    await db.refresh(new_host)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.create",
        entity_type="host",
        entity_id=new_host.id,
        meta={"name": new_host.name, "hostname": new_host.hostname, "port": new_host.port},
    )
    await dispatch_host_triggers(db, new_host, "host_created")
    return new_host


@router.get("/{host_id}", response_model=HostRead)
async def get_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    return host


@router.put("/{host_id}", response_model=HostRead)
async def update_host(
    host_id: int,
    payload: HostUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    updates = payload.model_dump(exclude_unset=True)
    previous_tags = dict(existing.tags or {})
    before = {}
    after = {}
    for key, value in updates.items():
        before[key] = getattr(existing, key, None)
        after[key] = value
    if "credential_id" in updates and updates["credential_id"]:
        secret = await db.get(Secret, int(updates["credential_id"]))
        if not secret or (secret.project_id is not None and secret.project_id != project_id):
            raise HTTPException(status_code=400, detail="Credential должен быть из текущего проекта или global")

    for field, value in updates.items():
        setattr(existing, field, value)
    await db.commit()
    await db.refresh(existing)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.update",
        entity_type="host",
        entity_id=existing.id,
        meta={"name": existing.name, "hostname": existing.hostname, "port": existing.port, "before": before, "after": after},
    )
    if updates.get("tags") is not None and dict(existing.tags or {}) != previous_tags:
        await dispatch_host_triggers(db, existing, "host_tags_changed")
    return existing


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_write)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    existing = res.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    await db.delete(existing)
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.delete",
        entity_type="host",
        entity_id=host_id,
        meta={"name": existing.name, "hostname": existing.hostname},
    )
    return None


@router.post("/{host_id}/status-check", response_model=HostStatusCheckResponse)
async def check_status(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_check)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host).where(Host.id == host_id).where(Host.project_id == project_id).where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    method = host.check_method or HostCheckMethod.tcp
    snapshot: Optional[dict[str, float | int]] = None
    if method == HostCheckMethod.ping:
        status_result = await _probe_ping(host)
    elif method == HostCheckMethod.ssh:
        status_result, snapshot = await _probe_ssh_health(host)
        if snapshot:
            host.health_snapshot = snapshot
            host.health_checked_at = datetime.utcnow()
    else:
        status_result = await _probe_tcp(host)
    host.status = status_result
    host.last_checked_at = datetime.utcnow()
    await db.commit()
    await db.refresh(host)
    db.add(
        HostHealthCheck(
            project_id=project_id,
            host_id=host.id,
            status=str(status_result.value if hasattr(status_result, "value") else status_result),
            snapshot=snapshot,
            checked_at=host.last_checked_at,
        )
    )
    await db.commit()
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.status_check",
        entity_type="host",
        entity_id=host.id,
        meta={"status": host.status, "method": str(method.value)},
    )
    if status_result == HostStatus.offline:
        await notify_event(
            db,
            project_id=project_id,
            event="host.offline",
            payload={"host_id": host.id, "hostname": host.hostname},
        )
    return host


@router.post("/{host_id}/facts-refresh", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def refresh_facts(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_run)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    query = await db.execute(
        select(Playbook).where(Playbook.project_id == project_id).where(Playbook.name == FACTS_PLAYBOOK_NAME)
    )
    playbook = query.scalar_one_or_none()
    if not playbook:
        playbook = Playbook(
            project_id=project_id,
            name=FACTS_PLAYBOOK_NAME,
            description="System playbook: facts collection",
            stored_content=FACTS_PLAYBOOK_CONTENT,
            variables={},
            inventory_scope=[],
            created_by=principal.id,
        )
        db.add(playbook)
        await db.commit()
        await db.refresh(playbook)

    snapshot_hosts = [
        {
            "id": host.id,
            "name": host.name,
            "hostname": host.hostname,
            "port": host.port,
            "username": host.username,
            "credential_id": host.credential_id,
        }
    ]
    run = JobRun(
        project_id=project_id,
        playbook_id=playbook.id,
        triggered_by=principal.email or "user",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": [],
            "host_ids": [host.id],
            "extra_vars": {"__facts_run": True},
            "dry_run": False,
            "facts_run": True,
            "params_before": {},
            "params_after": {"__facts_run": True},
        },
        logs="",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await enqueue_run(run.id, project_id=project_id)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.facts_refresh",
        entity_type="host",
        entity_id=host.id,
        meta={"run_id": run.id},
    )
    return run


@router.post("/{host_id}/actions", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def run_remote_action(
    host_id: int,
    payload: HostActionRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_run)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")

    query = await db.execute(
        select(Playbook).where(Playbook.project_id == project_id).where(Playbook.name == REMOTE_ACTIONS_PLAYBOOK_NAME)
    )
    playbook = query.scalar_one_or_none()
    if not playbook:
        playbook = Playbook(
            project_id=project_id,
            name=REMOTE_ACTIONS_PLAYBOOK_NAME,
            description="System playbook: remote actions",
            stored_content=REMOTE_ACTIONS_PLAYBOOK_CONTENT,
            variables={},
            inventory_scope=[],
            created_by=principal.id,
        )
        db.add(playbook)
        await db.commit()
        await db.refresh(playbook)

    if payload.action_type == "restart_service" and not payload.service_name:
        raise HTTPException(status_code=400, detail="service_name обязателен для restart_service")
    if payload.action_type == "fetch_logs" and not payload.log_path:
        raise HTTPException(status_code=400, detail="log_path обязателен для fetch_logs")
    if payload.action_type == "upload_file" and (not payload.file_dest or payload.file_content is None):
        raise HTTPException(status_code=400, detail="file_dest и file_content обязательны для upload_file")

    extra_vars = {
        "action_type": payload.action_type,
        "service_name": payload.service_name,
        "log_path": payload.log_path,
        "log_lines": payload.log_lines,
        "file_dest": payload.file_dest,
        "file_content": payload.file_content,
        "file_mode": payload.file_mode,
    }
    snapshot_hosts = [
        {
            "id": host.id,
            "name": host.name,
            "hostname": host.hostname,
            "port": host.port,
            "username": host.username,
            "credential_id": host.credential_id,
        }
    ]
    requires_approval = host.environment == "prod"
    run = JobRun(
        project_id=project_id,
        playbook_id=playbook.id,
        triggered_by=principal.email or "user",
        status=JobStatus.pending,
        target_snapshot={
            "hosts": snapshot_hosts,
            "group_ids": [],
            "host_ids": [host.id],
            "extra_vars": extra_vars,
            "dry_run": False,
            "remote_action": payload.action_type,
            "params_before": {},
            "params_after": extra_vars,
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
            action="host.remote_action_requires_approval",
            entity_type="run",
            entity_id=run.id,
            meta={"action": payload.action_type, "host_id": host.id, "approval_id": approval.id},
        )
        await notify_event(
            db,
            project_id=project_id,
            event="approval.requested",
            payload={"approval_id": approval.id, "run_id": run.id, "host_id": host.id},
        )
    else:
        await enqueue_run(run.id, project_id=project_id)
        await audit_log(
            db,
            project_id=project_id,
            actor=principal.email,
            actor_role=str(principal.role.value),
            action="host.remote_action",
            entity_type="run",
            entity_id=run.id,
            meta={"action": payload.action_type, "host_id": host.id},
        )
    return run


@router.post("/{host_id}/facts", status_code=status.HTTP_204_NO_CONTENT)
async def update_facts(
    host_id: int,
    payload: HostFactsUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.ansible_run)),
    project_id: int = Depends(get_current_project_id),
):
    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    host.facts_snapshot = payload.facts
    host.facts_checked_at = datetime.utcnow()
    await db.commit()
    await db.refresh(host)
    await audit_log(
        db,
        project_id=project_id,
        actor=principal.email,
        actor_role=str(principal.role.value),
        action="host.facts_update",
        entity_type="host",
        entity_id=host.id,
        meta={"facts_keys": len(payload.facts)},
    )
    return None


@router.get("/{host_id}/health-history", response_model=list[HostHealthHistoryRead])
async def health_history(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
    limit: int = Query(default=20, ge=1, le=200),
):
    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    query = await db.execute(
        select(HostHealthCheck)
        .where(HostHealthCheck.host_id == host_id)
        .where(HostHealthCheck.project_id == project_id)
        .order_by(HostHealthCheck.checked_at.desc())
        .limit(limit)
    )
    return query.scalars().all()


@router.get("/{host_id}/ssh-sessions", response_model=list[SshSessionRead])
async def list_ssh_sessions(
    host_id: int,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_permission(Permission.hosts_read)),
    project_id: int = Depends(get_current_project_id),
    limit: int = Query(default=20, ge=1, le=200),
):
    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Хост не найден")
    query = await db.execute(
        select(SshSession)
        .where(SshSession.host_id == host_id)
        .where(SshSession.project_id == project_id)
        .order_by(SshSession.started_at.desc())
        .limit(limit)
    )
    return query.scalars().all()


@router.websocket("/{host_id}/terminal")
async def host_terminal(
    websocket: WebSocket,
    host_id: int,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket -> SSH (PTY) терминал.

    Протокол сообщений:
    - по умолчанию: текстовые данные (как есть) — отправляются в stdin SSH процесса
    - опционально: JSON-команды
      - {"type":"resize","cols":123,"rows":45}
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    from app.core.security import verify_token

    try:
        payload = verify_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    role = payload.get("role", "user")
    if not has_permission(role, Permission.hosts_ssh):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    subject = payload.get("sub")
    if not subject:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    qp_project_id = websocket.query_params.get("project_id")
    if qp_project_id:
        try:
            requested_project_id = int(qp_project_id)
        except Exception:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    else:
        requested_project_id = None

    res = await db.execute(select(User).where(User.email == str(subject)))
    principal = res.scalar_one_or_none()
    if not principal:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        current_project_id = await resolve_current_project_id(db, principal, requested_project_id)
    except (ProjectNotFound, ProjectAccessDenied):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    res = await db.execute(
        select(Host)
        .where(Host.id == host_id)
        .where(Host.project_id == current_project_id)
        .where(host_access_clause(principal))
    )
    host = res.scalar_one_or_none()
    if not host:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WS terminal start host_id=%s user=%s", host_id, payload.get("sub"))
    await audit_log(
        db,
        project_id=current_project_id,
        actor=payload.get("sub"),
        actor_role=payload.get("role"),
        action="ssh.connect",
        entity_type="host",
        entity_id=host_id,
        meta={"hostname": host.hostname, "port": host.port, "username": host.username},
    )
    session = SshSession(
        project_id=current_project_id,
        host_id=host_id,
        actor=str(payload.get("sub")),
        source_ip=websocket.client.host if websocket.client else None,
        started_at=datetime.utcnow(),
        success=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    recording_enabled = bool(getattr(host, "record_ssh", False))
    transcript_parts: list[str] = []
    transcript_len = 0
    transcript_truncated = False
    max_transcript = 200_000

    def _append_transcript(prefix: str, text: str) -> None:
        nonlocal transcript_len, transcript_truncated
        if not recording_enabled or transcript_truncated:
            return
        chunk = f"{prefix} {text}"
        available = max_transcript - transcript_len
        if available <= 0:
            transcript_truncated = True
            return
        if len(chunk) > available:
            chunk = chunk[:available]
            transcript_truncated = True
        transcript_parts.append(chunk)
        transcript_len += len(chunk)
    password: Optional[str] = None
    private_key: Optional[str] = None
    passphrase: Optional[str] = None

    if host.credential:
        try:
            decrypted = decrypt_value(host.credential.encrypted_value)
            if host.credential.type == SecretType.password:
                password = decrypted
            elif host.credential.type == SecretType.private_key:
                private_key = decrypted
                if host.credential.encrypted_passphrase:
                    passphrase = decrypt_value(host.credential.encrypted_passphrase)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Не удалось расшифровать credential для host_id=%s: %s", host_id, exc)
            await websocket.send_text("Ошибка: не удалось расшифровать секрет для подключения.\n")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return

    try:
        conn = await asyncssh.connect(
            host.hostname,
            port=host.port,
            username=host.username,
            password=password,
            client_keys=[asyncssh.import_private_key(private_key, passphrase=passphrase)] if private_key else None,
            known_hosts=None,
            connect_timeout=10,
            keepalive_interval=30,
            keepalive_count_max=3,
            encoding=None,
        )
    except Exception as exc:
        logger.exception("SSH connect error host_id=%s: %s", host_id, exc)
        session.success = False
        session.error = str(exc)
        session.finished_at = datetime.utcnow()
        session.duration_seconds = int((session.finished_at - session.started_at).total_seconds())
        if recording_enabled:
            session.transcript = "".join(transcript_parts)
            session.transcript_truncated = transcript_truncated
        await db.commit()
        await websocket.send_text(f"SSH ошибка: {exc}\n")
        await audit_log(
            db,
            project_id=current_project_id,
            actor=payload.get("sub"),
            actor_role=payload.get("role"),
            action="ssh.connect_failed",
            entity_type="host",
            entity_id=host_id,
            success=False,
            meta={"error": str(exc)},
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    try:
        process = await conn.create_process(term_type="xterm-256color", term_size=(80, 24))
        process.stdin.write(b"\n")
        await process.stdin.drain()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось открыть shell host_id=%s: %s", host_id, exc)
        session.success = False
        session.error = str(exc)
        session.finished_at = datetime.utcnow()
        session.duration_seconds = int((session.finished_at - session.started_at).total_seconds())
        if recording_enabled:
            session.transcript = "".join(transcript_parts)
            session.transcript_truncated = transcript_truncated
        await db.commit()
        await websocket.send_text(f"Не удалось открыть shell: {exc}\n")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        conn.close()
        return

    async def _forward_stream(stream):
        try:
            while True:
                data = await stream.read(1024)
                if not data:
                    break
                # encoding=None => bytes
                if isinstance(data, (bytes, bytearray)):
                    text = bytes(data).decode(errors="ignore")
                    _append_transcript("OUT:", text)
                    await websocket.send_text(text)
                else:
                    text = str(data)
                    _append_transcript("OUT:", text)
                    await websocket.send_text(text)
        except Exception as exc:  # noqa: BLE001
            logger.debug("stdout/stderr stream closed: %s", exc)

    session_error: Optional[str] = None

    async def _forward_ws():
        nonlocal session_error
        try:
            async for message in websocket.iter_text():
                if message and message[0] == "{":
                    try:
                        obj = json.loads(message)
                    except Exception:
                        obj = None
                    if isinstance(obj, dict):
                        message_type = obj.get("type")
                        if message_type == "resize":
                            cols = int(obj.get("cols", 80))
                            rows = int(obj.get("rows", 24))
                            cols = max(20, min(cols, 500))
                            rows = max(5, min(rows, 200))
                            process.change_terminal_size(cols, rows)
                            continue
                # обычные данные терминала
                data = message.encode("utf-8", errors="ignore")
                _append_transcript("IN:", message)
                process.stdin.write(data)
                await process.stdin.drain()
        except WebSocketDisconnect:
            logger.info("WS закрыт клиентом host_id=%s", host_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ошибка чтения WS host_id=%s: %s", host_id, exc)
            session_error = str(exc)

    stdout_task = asyncio.create_task(_forward_stream(process.stdout))
    stderr_task = asyncio.create_task(_forward_stream(process.stderr))
    ws_task = asyncio.create_task(_forward_ws())
    exit_task = asyncio.create_task(process.wait())

    # Держим сессию пока клиент не закроет WS или пока не завершится shell.
    done, pending = await asyncio.wait({ws_task, exit_task}, return_when=asyncio.FIRST_COMPLETED)

    for task in (stdout_task, stderr_task, ws_task, exit_task):
        if task not in done:
            task.cancel()

    try:
        process.stdin.write_eof()
    except Exception:
        pass
    try:
        process.kill()
        await process.wait()
    except Exception:
        pass
    conn.close()
    session.finished_at = datetime.utcnow()
    session.duration_seconds = int((session.finished_at - session.started_at).total_seconds())
    if session_error:
        session.success = False
        session.error = session_error
    if recording_enabled:
        session.transcript = "".join(transcript_parts)
        session.transcript_truncated = transcript_truncated
    await db.commit()
    await audit_log(
        db,
        project_id=current_project_id,
        actor=payload.get("sub"),
        actor_role=payload.get("role"),
        action="ssh.disconnect",
        entity_type="host",
        entity_id=host_id,
        meta={"hostname": host.hostname, "port": host.port},
    )

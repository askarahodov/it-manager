"""Модели для основной доменной области."""

from datetime import datetime
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Project(Base):
    """Проект (tenant) — изоляция инфраструктур (hosts/groups/secrets/playbooks/runs).

    MVP:
    - все пользователи видят все проекты (ограничения по проектам добавим позже);
    - по умолчанию создаётся проект `default`.
    """

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class HostStatus(str, enum.Enum):
    unknown = "unknown"
    online = "online"
    offline = "offline"


class HostCheckMethod(str, enum.Enum):
    ping = "ping"
    tcp = "tcp"
    ssh = "ssh"


class SecretType(str, enum.Enum):
    text = "text"
    password = "password"
    token = "token"
    private_key = "private_key"


class PluginType(str, enum.Enum):
    inventory = "inventory"
    secrets = "secrets"
    automation = "automation"


class UserRole(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    viewer = "viewer"
    automation_only = "automation-only"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    # Ограничения доступа (MVP):
    # - allowed_environments: список environment, к которым есть доступ (None => все).
    # - allowed_group_ids: список group_id, к которым есть доступ (None => все).
    # - allowed_project_ids: список project_id, к которым есть доступ (None => все).
    # Важно: пустой список означает "нет доступа никуда".
    allowed_environments = Column(JSONB, nullable=True)
    allowed_group_ids = Column(JSONB, nullable=True)
    allowed_project_ids = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Secret(Base):
    __tablename__ = "secrets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, default=1, index=True)
    name = Column(String, nullable=False)
    type = Column(Enum(SecretType), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    encrypted_passphrase = Column(Text, nullable=True)
    scope = Column(String, default="project")
    description = Column(Text, nullable=True)
    tags = Column(JSONB, default=dict)
    expires_at = Column(DateTime, nullable=True)
    rotation_interval_days = Column(Integer, nullable=True)
    last_rotated_at = Column(DateTime, nullable=True)
    next_rotated_at = Column(DateTime, nullable=True)
    dynamic_enabled = Column(Boolean, default=False, nullable=False)
    dynamic_ttl_seconds = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class PluginInstance(Base):
    __tablename__ = "plugin_instances"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    type = Column(Enum(PluginType), nullable=False)
    definition_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    config = Column(JSONB, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class Host(Base):
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    name = Column(String, nullable=False)
    hostname = Column(String, nullable=False, index=True)
    port = Column(Integer, default=22, nullable=False)
    username = Column(String, default="root", nullable=False)
    os_type = Column(String, default="linux")
    environment = Column(String, default="prod")
    tags = Column(JSONB, default=dict)
    description = Column(Text, nullable=True)
    status = Column(Enum(HostStatus), default=HostStatus.unknown)
    check_method = Column(Enum(HostCheckMethod), default=HostCheckMethod.tcp, nullable=False)
    last_checked_at = Column(DateTime, nullable=True)
    last_run_id = Column(Integer, nullable=True)
    last_run_status = Column(String, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    health_snapshot = Column(JSONB, nullable=True)
    health_checked_at = Column(DateTime, nullable=True)
    facts_snapshot = Column(JSONB, nullable=True)
    facts_checked_at = Column(DateTime, nullable=True)
    record_ssh = Column(Boolean, default=False, nullable=False)
    credential_id = Column(Integer, ForeignKey("secrets.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())

    credential = relationship("Secret", lazy="joined")


class SecretLease(Base):
    __tablename__ = "secret_leases"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    secret_id = Column(Integer, ForeignKey("secrets.id"), nullable=False, index=True)
    issued_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    issued_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    encrypted_value = Column(Text, nullable=False)


class HostHealthCheck(Base):
    __tablename__ = "host_health_checks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    snapshot = Column(JSONB, nullable=True)
    checked_at = Column(DateTime, server_default=func.now())


class SshSession(Base):
    __tablename__ = "ssh_sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False, index=True)
    actor = Column(String, nullable=False)
    source_ip = Column(String, nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    success = Column(Boolean, default=True, nullable=False)
    error = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    transcript_truncated = Column(Boolean, default=False, nullable=False)


class GroupType(str, enum.Enum):
    static = "static"
    dynamic = "dynamic"


class HostGroup(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    name = Column(String, nullable=False)
    type = Column(Enum(GroupType), nullable=False)
    rule = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())

    hosts = relationship("GroupHost", cascade="all, delete-orphan", back_populates="group")


class GroupHost(Base):
    """Связь хоста с группой (для статических групп).

    Для динамических групп используется отдельный кэш (см. DynamicGroupHostCache),
    чтобы быстро отдавать состав без пересчёта на каждый запрос.
    """

    __tablename__ = "group_hosts"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False)
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    group = relationship("HostGroup", back_populates="hosts")
    host = relationship("Host")


class DynamicGroupHostCache(Base):
    """Кэш состава динамической группы.

    Заполняется воркером и/или ручным запросом пересчёта.
    """

    __tablename__ = "dynamic_group_host_cache"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=False)
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="CASCADE"), index=True, nullable=False)
    computed_at = Column(DateTime, server_default=func.now(), nullable=False)

    host = relationship("Host")


class Playbook(Base):
    __tablename__ = "playbooks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    repo_url = Column(String, nullable=True)
    repo_ref = Column(String, nullable=True)
    repo_playbook_path = Column(String, nullable=True)
    repo_auto_sync = Column(Boolean, default=False, nullable=False)
    repo_last_sync_at = Column(DateTime, nullable=True)
    repo_last_commit = Column(String, nullable=True)
    repo_sync_status = Column(String, nullable=True)
    repo_sync_message = Column(Text, nullable=True)
    repo_path = Column(String, nullable=True)
    stored_content = Column(Text, nullable=True)
    inventory_scope = Column(JSONB, default=list)
    variables = Column(JSONB, default=dict)
    webhook_token = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class PlaybookTemplate(Base):
    __tablename__ = "playbook_templates"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    vars_schema = Column(JSONB, default=dict)
    vars_defaults = Column(JSONB, default=dict)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class PlaybookInstance(Base):
    __tablename__ = "playbook_instances"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    template_id = Column(Integer, ForeignKey("playbook_templates.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    values = Column(JSONB, default=dict)
    host_ids = Column(JSONB, default=list)
    group_ids = Column(JSONB, default=list)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class PlaybookTrigger(Base):
    __tablename__ = "playbook_triggers"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    type = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    filters = Column(JSONB, default=dict)
    extra_vars = Column(JSONB, default=dict)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    playbook_id = Column(Integer, ForeignKey("playbooks.id"), nullable=False)
    triggered_by = Column(String, nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    target_snapshot = Column(JSONB, default=dict)
    logs = Column(Text, default="")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    run_id = Column(Integer, ForeignKey("job_runs.id"), nullable=False, index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(ApprovalStatus), default=ApprovalStatus.pending, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    decided_at = Column(DateTime, nullable=True)


class AuditEvent(Base):
    """Аудит событий (CRUD, SSH, Automation).

    Не хранит содержимое секретов или команд терминала.
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    actor = Column(String, nullable=False)  # email/subject
    actor_role = Column(String, nullable=True)
    action = Column(String, nullable=False)  # например: host.create, ssh.connect
    entity_type = Column(String, nullable=True)  # host/secret/group/playbook/run
    entity_id = Column(Integer, nullable=True)
    success = Column(Integer, default=1, nullable=False)  # 1/0
    meta = Column(JSONB, default=dict)  # безопасные метаданные
    source_ip = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class NotificationEndpoint(Base):
    __tablename__ = "notification_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, default=1, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default="webhook")
    url = Column(String, nullable=False)
    secret = Column(String, nullable=True)
    events = Column(JSONB, default=list)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    key = Column(String, primary_key=True)
    value = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow())

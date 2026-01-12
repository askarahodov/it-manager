"""Модели для основной доменной области."""

from datetime import datetime
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
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
    credential_id = Column(Integer, ForeignKey("secrets.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=datetime.utcnow())

    credential = relationship("Secret", lazy="joined")


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
    repo_path = Column(String, nullable=True)
    stored_content = Column(Text, nullable=True)
    inventory_scope = Column(JSONB, default=list)
    variables = Column(JSONB, default=dict)
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
    created_at = Column(DateTime, server_default=func.now(), index=True)

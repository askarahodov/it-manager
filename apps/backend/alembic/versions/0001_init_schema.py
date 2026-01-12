"""0001: начальная схема (idempotent для старых create_all БД).

Revision ID: 0001_init_schema
Revises: 
Create Date: 2025-12-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


revision = "0001_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Если БД уже инициализирована старым create_all — не ломаемся.
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if existing:
        return

    hoststatus = sa.Enum("unknown", "online", "offline", name="hoststatus")
    secrettype = sa.Enum("text", "password", "token", "private_key", name="secrettype")
    userrole = sa.Enum("admin", "user", name="userrole")
    grouptype = sa.Enum("static", "dynamic", name="grouptype")
    jobstatus = sa.Enum("pending", "running", "success", "failed", name="jobstatus")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", userrole, nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "secrets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", secrettype, nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("encrypted_passphrase", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False, server_default="global"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_secrets_id", "secrets", ["id"])

    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("hostname", sa.String(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.String(), nullable=False, server_default="root"),
        sa.Column("os_type", sa.String(), nullable=False, server_default="linux"),
        sa.Column("environment", sa.String(), nullable=False, server_default="prod"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", hoststatus, nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("credential_id", sa.Integer(), sa.ForeignKey("secrets.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_hosts_id", "hosts", ["id"])
    op.create_index("ix_hosts_hostname", "hosts", ["hostname"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", grouptype, nullable=False),
        sa.Column("rule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_groups_id", "groups", ["id"])

    op.create_table(
        "group_hosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_group_hosts_group_id", "group_hosts", ["group_id"])
    op.create_index("ix_group_hosts_host_id", "group_hosts", ["host_id"])

    op.create_table(
        "dynamic_group_host_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dynamic_group_host_cache_group_id", "dynamic_group_host_cache", ["group_id"])
    op.create_index("ix_dynamic_group_host_cache_host_id", "dynamic_group_host_cache", ["host_id"])

    op.create_table(
        "playbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repo_path", sa.String(), nullable=True),
        sa.Column("stored_content", sa.Text(), nullable=True),
        sa.Column("inventory_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_playbooks_id", "playbooks", ["id"])

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("playbook_id", sa.Integer(), sa.ForeignKey("playbooks.id"), nullable=False),
        sa.Column("triggered_by", sa.String(), nullable=False),
        sa.Column("status", jobstatus, nullable=False, server_default="pending"),
        sa.Column("target_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("logs", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_job_runs_id", "job_runs", ["id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("success", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_events_id", "audit_events", ["id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    # downgrade для MVP используем редко; best-effort
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return

    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_job_runs_id", table_name="job_runs")
    op.drop_table("job_runs")

    op.drop_index("ix_playbooks_id", table_name="playbooks")
    op.drop_table("playbooks")

    op.drop_index("ix_dynamic_group_host_cache_host_id", table_name="dynamic_group_host_cache")
    op.drop_index("ix_dynamic_group_host_cache_group_id", table_name="dynamic_group_host_cache")
    op.drop_table("dynamic_group_host_cache")

    op.drop_index("ix_group_hosts_host_id", table_name="group_hosts")
    op.drop_index("ix_group_hosts_group_id", table_name="group_hosts")
    op.drop_table("group_hosts")

    op.drop_index("ix_groups_id", table_name="groups")
    op.drop_table("groups")

    op.drop_index("ix_hosts_hostname", table_name="hosts")
    op.drop_index("ix_hosts_id", table_name="hosts")
    op.drop_table("hosts")

    op.drop_index("ix_secrets_id", table_name="secrets")
    op.drop_table("secrets")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    # enum types drop (best-effort)
    for enum_name in ["jobstatus", "grouptype", "userrole", "secrettype", "hoststatus"]:
        try:
            op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))
        except Exception:
            pass


"""0004: Projects/Tenants (project_id для доменных сущностей).

Revision ID: 0004_projects_tenants
Revises: 0003_rbac2_users_scope
Create Date: 2025-12-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "0004_projects_tenants"
down_revision = "0003_rbac2_users_scope"
branch_labels = None
depends_on = None


def _ensure_default_project(bind) -> None:
    bind.execute(
        text(
            """
            INSERT INTO projects (id, name, description, created_at)
            VALUES (1, 'default', 'Проект по умолчанию (dev)', now())
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    # Подтянем sequence, если она есть.
    bind.execute(
        text(
            """
            WITH seq AS (
              SELECT pg_get_serial_sequence('projects', 'id') AS seqname
            )
            SELECT setval(
              seq.seqname,
              (SELECT COALESCE(MAX(id), 1) FROM projects)
            )
            FROM seq
            WHERE seq.seqname IS NOT NULL
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Если миграция уже применялась через create_all/ручные изменения — не ломаемся.
    existing = bind.execute(text("SELECT to_regclass('public.projects')")).scalar()
    if not existing:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        )
        op.create_index("ix_projects_id", "projects", ["id"])
        op.create_index("ix_projects_name", "projects", ["name"], unique=True)

    _ensure_default_project(bind)

    def _add_project_id(table: str, *, nullable: bool) -> None:
        # idempotent: добавляем только если колонки нет
        col_exists = bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:t AND column_name='project_id'
                """
            ),
            {"t": table},
        ).scalar()
        if col_exists:
            return
        op.add_column(table, sa.Column("project_id", sa.Integer(), nullable=True, server_default=sa.text("1")))
        op.create_index(f"ix_{table}_project_id", table, ["project_id"])
        op.create_foreign_key(f"fk_{table}_project_id_projects", table, "projects", ["project_id"], ["id"])
        # backfill + NOT NULL для доменных сущностей
        bind.execute(text(f"UPDATE {table} SET project_id=1 WHERE project_id IS NULL"))
        if not nullable:
            op.alter_column(table, "project_id", nullable=False, server_default=None)

    _add_project_id("hosts", nullable=False)
    _add_project_id("groups", nullable=False)
    _add_project_id("secrets", nullable=False)
    _add_project_id("playbooks", nullable=False)
    _add_project_id("job_runs", nullable=False)
    _add_project_id("audit_events", nullable=True)


def downgrade() -> None:
    bind = op.get_bind()

    def _drop_project_id(table: str) -> None:
        col_exists = bind.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:t AND column_name='project_id'
                """
            ),
            {"t": table},
        ).scalar()
        if not col_exists:
            return
        try:
            op.drop_constraint(f"fk_{table}_project_id_projects", table_name=table, type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_index(f"ix_{table}_project_id", table_name=table)
        except Exception:
            pass
        op.drop_column(table, "project_id")

    for t in ["audit_events", "job_runs", "playbooks", "secrets", "groups", "hosts"]:
        _drop_project_id(t)

    existing = bind.execute(text("SELECT to_regclass('public.projects')")).scalar()
    if existing:
        try:
            op.drop_index("ix_projects_name", table_name="projects")
            op.drop_index("ix_projects_id", table_name="projects")
        except Exception:
            pass
        op.drop_table("projects")

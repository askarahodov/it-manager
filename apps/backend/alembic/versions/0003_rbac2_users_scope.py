"""0003: RBAC 2.0 роли + поля ограничений (env/groups).

Добавляет значения в postgres enum userrole и расширяет таблицу users.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


revision = "0003_rbac2_users_scope"
down_revision = "0002_host_check_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.users')")).scalar()
    if not existing:
        return

    # Обновляем enum userrole (Postgres не поддерживает DROP VALUE, поэтому downgrade best-effort).
    for value in ["operator", "viewer", "automation-only"]:
        op.execute(sa.text(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{value}'"))

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("allowed_environments", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch.add_column(sa.Column("allowed_group_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.users')")).scalar()
    if not existing:
        return

    with op.batch_alter_table("users") as batch:
        batch.drop_column("allowed_group_ids")
        batch.drop_column("allowed_environments")

    # Значения enum userrole не удаляем (ограничение Postgres).


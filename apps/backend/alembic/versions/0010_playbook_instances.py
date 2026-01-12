"""0010: playbook instances (values + bindings)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0010_playbook_instances"
down_revision = "0009_playbook_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbook_templates')")).scalar()
    if not existing:
        return
    op.create_table(
        "playbook_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("playbook_templates.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("host_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("group_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_playbook_instances_id", "playbook_instances", ["id"])
    op.create_index("ix_playbook_instances_project_id", "playbook_instances", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbook_instances')")).scalar()
    if not existing:
        return
    op.drop_index("ix_playbook_instances_project_id", table_name="playbook_instances")
    op.drop_index("ix_playbook_instances_id", table_name="playbook_instances")
    op.drop_table("playbook_instances")


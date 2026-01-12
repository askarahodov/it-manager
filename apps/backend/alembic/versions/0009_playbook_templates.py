"""0009: playbook templates (vars schema + defaults)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0009_playbook_templates"
down_revision = "0008_hosts_last_run_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.projects')")).scalar()
    if not existing:
        return
    op.create_table(
        "playbook_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vars_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("vars_defaults", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_playbook_templates_id", "playbook_templates", ["id"])
    op.create_index("ix_playbook_templates_project_id", "playbook_templates", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbook_templates')")).scalar()
    if not existing:
        return
    op.drop_index("ix_playbook_templates_project_id", table_name="playbook_templates")
    op.drop_index("ix_playbook_templates_id", table_name="playbook_templates")
    op.drop_table("playbook_templates")


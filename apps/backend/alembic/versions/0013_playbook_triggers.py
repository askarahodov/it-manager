"""0013: playbook triggers."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0013_playbook_triggers"
down_revision = "0012_playbook_webhook_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbook_triggers')")).scalar()
    if existing:
        return
    op.create_table(
        "playbook_triggers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("playbook_id", sa.Integer(), sa.ForeignKey("playbooks.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("extra_vars", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_playbook_triggers_id", "playbook_triggers", ["id"])
    op.create_index("ix_playbook_triggers_project_id", "playbook_triggers", ["project_id"])
    op.create_index("ix_playbook_triggers_playbook_id", "playbook_triggers", ["playbook_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbook_triggers')")).scalar()
    if not existing:
        return
    op.drop_index("ix_playbook_triggers_playbook_id", table_name="playbook_triggers")
    op.drop_index("ix_playbook_triggers_project_id", table_name="playbook_triggers")
    op.drop_index("ix_playbook_triggers_id", table_name="playbook_triggers")
    op.drop_table("playbook_triggers")

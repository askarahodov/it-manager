"""0015: host health history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0015_host_health_history"
down_revision = "0014_hosts_health_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.host_health_checks')")).scalar()
    if existing:
        return
    op.create_table(
        "host_health_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.text("now()")),
    )
    op.create_index("ix_host_health_checks_id", "host_health_checks", ["id"])
    op.create_index("ix_host_health_checks_host_id", "host_health_checks", ["host_id"])
    op.create_index("ix_host_health_checks_project_id", "host_health_checks", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.host_health_checks')")).scalar()
    if not existing:
        return
    op.drop_index("ix_host_health_checks_project_id", table_name="host_health_checks")
    op.drop_index("ix_host_health_checks_host_id", table_name="host_health_checks")
    op.drop_index("ix_host_health_checks_id", table_name="host_health_checks")
    op.drop_table("host_health_checks")

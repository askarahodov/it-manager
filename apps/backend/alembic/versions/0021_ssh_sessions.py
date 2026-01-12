"""0021: ssh sessions metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0021_ssh_sessions"
down_revision = "0020_notification_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.ssh_sessions')")).scalar()
    if existing:
        return
    op.create_table(
        "ssh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("host_id", sa.Integer(), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("source_ip", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_ssh_sessions_id", "ssh_sessions", ["id"])
    op.create_index("ix_ssh_sessions_project_id", "ssh_sessions", ["project_id"])
    op.create_index("ix_ssh_sessions_host_id", "ssh_sessions", ["host_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.ssh_sessions')")).scalar()
    if not existing:
        return
    op.drop_index("ix_ssh_sessions_host_id", table_name="ssh_sessions")
    op.drop_index("ix_ssh_sessions_project_id", table_name="ssh_sessions")
    op.drop_index("ix_ssh_sessions_id", table_name="ssh_sessions")
    op.drop_table("ssh_sessions")

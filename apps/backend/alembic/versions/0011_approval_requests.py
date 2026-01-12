"""0011: approval requests for runs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0011_approval_requests"
down_revision = "0010_playbook_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.job_runs')")).scalar()
    if not existing:
        return
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False, server_default="1"),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("job_runs.id"), nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_approval_requests_id", "approval_requests", ["id"])
    op.create_index("ix_approval_requests_project_id", "approval_requests", ["project_id"])
    op.create_index("ix_approval_requests_run_id", "approval_requests", ["run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.approval_requests')")).scalar()
    if not existing:
        return
    op.drop_index("ix_approval_requests_run_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_project_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_id", table_name="approval_requests")
    op.drop_table("approval_requests")


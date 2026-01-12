"""0014: host health snapshot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0014_hosts_health_snapshot"
down_revision = "0013_playbook_triggers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    op.add_column("hosts", sa.Column("health_snapshot", sa.JSON(), nullable=True))
    op.add_column("hosts", sa.Column("health_checked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    op.drop_column("hosts", "health_checked_at")
    op.drop_column("hosts", "health_snapshot")

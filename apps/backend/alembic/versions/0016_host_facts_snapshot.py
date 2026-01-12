"""0016: host facts snapshot."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0016_host_facts_snapshot"
down_revision = "0015_host_health_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    op.add_column("hosts", sa.Column("facts_snapshot", sa.JSON(), nullable=True))
    op.add_column("hosts", sa.Column("facts_checked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if not existing:
        return
    op.drop_column("hosts", "facts_checked_at")
    op.drop_column("hosts", "facts_snapshot")

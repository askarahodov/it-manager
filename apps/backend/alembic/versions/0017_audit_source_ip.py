"""0017: audit source ip."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0017_audit_source_ip"
down_revision = "0016_host_facts_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.audit_events')")).scalar()
    if not existing:
        return
    op.add_column("audit_events", sa.Column("source_ip", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.audit_events')")).scalar()
    if not existing:
        return
    op.drop_column("audit_events", "source_ip")

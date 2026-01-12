"""0018: secrets expires_at."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0018_secrets_expires_at"
down_revision = "0017_audit_source_ip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    op.add_column("secrets", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.secrets')")).scalar()
    if not existing:
        return
    op.drop_column("secrets", "expires_at")

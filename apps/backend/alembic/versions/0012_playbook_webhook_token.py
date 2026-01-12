"""0012: playbook webhook token."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0012_playbook_webhook_token"
down_revision = "0011_approval_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbooks')")).scalar()
    if not existing:
        return
    op.add_column("playbooks", sa.Column("webhook_token", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    existing = bind.execute(text("SELECT to_regclass('public.playbooks')")).scalar()
    if not existing:
        return
    op.drop_column("playbooks", "webhook_token")

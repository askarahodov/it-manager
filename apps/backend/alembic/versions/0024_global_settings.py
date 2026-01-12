"""0024: global settings."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024_global_settings"
down_revision = "0023_playbook_git_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "global_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("global_settings")

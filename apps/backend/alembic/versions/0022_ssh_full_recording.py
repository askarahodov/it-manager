"""0022: ssh full recording."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0022_ssh_full_recording"
down_revision = "0021_ssh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    hosts = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if hosts:
        op.add_column("hosts", sa.Column("record_ssh", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    sessions = bind.execute(text("SELECT to_regclass('public.ssh_sessions')")).scalar()
    if sessions:
        op.add_column("ssh_sessions", sa.Column("transcript", sa.Text(), nullable=True))
        op.add_column("ssh_sessions", sa.Column("transcript_truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    bind = op.get_bind()
    sessions = bind.execute(text("SELECT to_regclass('public.ssh_sessions')")).scalar()
    if sessions:
        op.drop_column("ssh_sessions", "transcript_truncated")
        op.drop_column("ssh_sessions", "transcript")
    hosts = bind.execute(text("SELECT to_regclass('public.hosts')")).scalar()
    if hosts:
        op.drop_column("hosts", "record_ssh")

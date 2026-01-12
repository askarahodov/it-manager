"""0023: playbook git sync metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0023_playbook_git_sync"
down_revision = "0022_ssh_full_recording"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    playbooks = bind.execute(text("SELECT to_regclass('public.playbooks')")).scalar()
    if playbooks:
        op.add_column("playbooks", sa.Column("repo_url", sa.String(), nullable=True))
        op.add_column("playbooks", sa.Column("repo_ref", sa.String(), nullable=True))
        op.add_column("playbooks", sa.Column("repo_playbook_path", sa.String(), nullable=True))
        op.add_column(
            "playbooks",
            sa.Column("repo_auto_sync", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.add_column("playbooks", sa.Column("repo_last_sync_at", sa.DateTime(), nullable=True))
        op.add_column("playbooks", sa.Column("repo_last_commit", sa.String(), nullable=True))
        op.add_column("playbooks", sa.Column("repo_sync_status", sa.String(), nullable=True))
        op.add_column("playbooks", sa.Column("repo_sync_message", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    playbooks = bind.execute(text("SELECT to_regclass('public.playbooks')")).scalar()
    if playbooks:
        op.drop_column("playbooks", "repo_sync_message")
        op.drop_column("playbooks", "repo_sync_status")
        op.drop_column("playbooks", "repo_last_commit")
        op.drop_column("playbooks", "repo_last_sync_at")
        op.drop_column("playbooks", "repo_auto_sync")
        op.drop_column("playbooks", "repo_playbook_path")
        op.drop_column("playbooks", "repo_ref")
        op.drop_column("playbooks", "repo_url")

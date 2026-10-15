"""conversation agent state

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: 0001 snapshots current model metadata, so fresh databases may already have it
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS state JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS state")

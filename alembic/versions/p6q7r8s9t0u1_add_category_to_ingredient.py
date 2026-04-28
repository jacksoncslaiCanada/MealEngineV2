"""add category to ingredient

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'p6q7r8s9t0u1'
down_revision = 'o5p6q7r8s9t0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS guards against the column already being present
    # (e.g. added manually before this migration ran).
    op.execute(
        "ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS category VARCHAR(32)"
    )


def downgrade() -> None:
    op.drop_column('ingredients', 'category')

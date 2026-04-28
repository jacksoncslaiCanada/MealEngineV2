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
    op.add_column(
        'ingredients',
        sa.Column('category', sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ingredients', 'category')

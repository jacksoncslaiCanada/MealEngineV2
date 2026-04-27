"""add blueprint_role to raw_recipe

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'o5p6q7r8s9t0'
down_revision = 'n4o5p6q7r8s9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'raw_recipes',
        sa.Column('blueprint_role', sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('raw_recipes', 'blueprint_role')

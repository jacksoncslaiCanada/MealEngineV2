"""add course to raw_recipe

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'n4o5p6q7r8s9'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'raw_recipes',
        sa.Column('course', sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('raw_recipes', 'course')

"""add macros and side_suggestion to raw_recipe

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa

revision = 'q7r8s9t0u1v2'
down_revision = 'p6q7r8s9t0u1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw_recipes ADD COLUMN IF NOT EXISTS calories INTEGER")
    op.execute("ALTER TABLE raw_recipes ADD COLUMN IF NOT EXISTS protein_g INTEGER")
    op.execute("ALTER TABLE raw_recipes ADD COLUMN IF NOT EXISTS carbs_g INTEGER")
    op.execute("ALTER TABLE raw_recipes ADD COLUMN IF NOT EXISTS fat_g INTEGER")
    op.execute("ALTER TABLE raw_recipes ADD COLUMN IF NOT EXISTS side_suggestion TEXT")


def downgrade() -> None:
    op.drop_column('raw_recipes', 'side_suggestion')
    op.drop_column('raw_recipes', 'fat_g')
    op.drop_column('raw_recipes', 'carbs_g')
    op.drop_column('raw_recipes', 'protein_g')
    op.drop_column('raw_recipes', 'calories')

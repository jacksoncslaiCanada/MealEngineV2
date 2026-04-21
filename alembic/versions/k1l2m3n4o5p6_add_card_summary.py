"""add_card_summary_to_raw_recipes

Adds card_summary (plain text, 2-3 sentence enticing headnote) to raw_recipes.
Generated alongside card_steps and card_tip by Claude Haiku in a single call.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_recipes", sa.Column("card_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "card_summary")

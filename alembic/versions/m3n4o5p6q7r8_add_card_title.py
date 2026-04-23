"""add_card_title_to_raw_recipes

Adds card_title column to raw_recipes. Stores a clean, AI-generated
dish name (e.g. "Crispy Garlic Butter Chicken") so the recipe card
always has a proper title regardless of raw content format.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa

revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_recipes", sa.Column("card_title", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "card_title")

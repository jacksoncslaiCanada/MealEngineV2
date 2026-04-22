"""add_card_image_url_to_raw_recipes

Adds card_image_url column to raw_recipes. Stores the resolved,
ready-to-embed image URL for the recipe card — either a YouTube
thumbnail or a Flux-generated image uploaded to Supabase Storage.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa

revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_recipes", sa.Column("card_image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_recipes", "card_image_url")

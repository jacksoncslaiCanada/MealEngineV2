"""add_recipe_components_table

Adds the recipe_components table for the Blueprint component view.
Each row is a named meal component (base/flavor/protein/other) inferred
from a recipe's ingredients by Claude Haiku.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_components",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recipe_id", sa.Integer(), sa.ForeignKey("raw_recipes.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_recipe_components_recipe_id", "recipe_components", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("ix_recipe_components_recipe_id", table_name="recipe_components")
    op.drop_table("recipe_components")

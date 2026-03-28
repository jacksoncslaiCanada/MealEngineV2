"""relax_ingredients_legacy_not_null

The live `ingredients` table was created before Phase 2 migrations ran and
contains extra columns (name, normalized_name, category) that are NOT NULL but
are not managed by our ORM.  Our INSERT does not supply these columns, causing
a NOT NULL violation.

This migration makes those three legacy columns nullable so our INSERTs succeed.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-03-28 02:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "a6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None

_LEGACY_COLUMNS = ["name", "normalized_name", "category"]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Only act if the ingredients table exists
    if "ingredients" not in inspector.get_table_names():
        return

    existing_cols = {c["name"]: c for c in inspector.get_columns("ingredients")}

    for col_name in _LEGACY_COLUMNS:
        if col_name not in existing_cols:
            continue
        col_info = existing_cols[col_name]
        # Skip if already nullable
        if col_info.get("nullable", True):
            continue
        # ALTER COLUMN … DROP NOT NULL
        col_type = col_info["type"]
        op.alter_column(
            "ingredients",
            col_name,
            existing_type=col_type,
            nullable=True,
        )


def downgrade() -> None:
    # Reversing this would require re-adding NOT NULL, which could fail if
    # NULLs are already present.  Leave as a no-op for safety.
    pass

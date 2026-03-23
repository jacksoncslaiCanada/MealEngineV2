"""patch_sources_missing_columns

Idempotent guard that adds any Phase 1 columns still missing from the
`sources` table.

Background
----------
Migration a9f2b1c3d4e5 had an `else` branch intended to backfill columns
onto a pre-existing `sources` table, but the production database shows
the seven columns below are absent while the `raw_recipes` Phase 1 columns
are present.  This migration repairs the gap unconditionally so that
`alembic upgrade head` is safe to re-run on both affected and healthy DBs.

Revision ID: b1c3d4e5f6a7
Revises: a9f2b1c3d4e5
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision: str = "b1c3d4e5f6a7"
down_revision: Union[str, None] = "a9f2b1c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Columns that must exist on `sources` after this migration.
# All are nullable=True so the ADD COLUMN succeeds even when rows already exist.
_REQUIRED_COLUMNS = [
    ("platform",          sa.Column("platform",          sa.String(16),              nullable=True)),
    ("handle",            sa.Column("handle",            sa.String(256),             nullable=True)),
    ("display_name",      sa.Column("display_name",      sa.String(256),             nullable=True)),
    ("quality_score",     sa.Column("quality_score",     sa.Float(),                 nullable=True)),
    ("content_count",     sa.Column("content_count",     sa.Integer(),               nullable=True, server_default="0")),
    ("added_at",          sa.Column("added_at",          sa.DateTime(timezone=True), nullable=True)),
    ("last_ingested_at",  sa.Column("last_ingested_at",  sa.DateTime(timezone=True), nullable=True)),
]

_REQUIRED_CONSTRAINTS = [
    # name, columns
    ("uq_source_platform_handle", ("platform", "handle")),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    # ── 1. Add any missing columns ────────────────────────────────────────────
    existing_cols = {c["name"] for c in inspector.get_columns("sources")}
    for col_name, col_def in _REQUIRED_COLUMNS:
        if col_name not in existing_cols:
            op.add_column("sources", col_def)

    # ── 2. Add the unique constraint if it is absent ──────────────────────────
    # Re-inspect after column additions so the constraint check is accurate.
    existing_constraints = {
        uc["name"]
        for uc in inspector.get_unique_constraints("sources")
    }
    for constraint_name, columns in _REQUIRED_CONSTRAINTS:
        if constraint_name not in existing_constraints:
            op.create_unique_constraint(constraint_name, "sources", list(columns))


def downgrade() -> None:
    # Remove the unique constraint first, then the columns.
    op.drop_constraint("uq_source_platform_handle", "sources", type_="unique")
    for col_name, _ in reversed(_REQUIRED_COLUMNS):
        op.drop_column("sources", col_name)

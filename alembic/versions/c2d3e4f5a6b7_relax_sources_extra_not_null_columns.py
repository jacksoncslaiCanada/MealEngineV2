"""relax_sources_extra_not_null_columns

The production `sources` table contains columns that were added outside of
the Phase 1 migration chain: channel, created_at, duration_seconds,
error_reason, language, source_type, url.

At least `url` is defined NOT NULL without a server default.  Because the
Phase 1 ORM model (app/db/models.py :: Source) does not include these
columns, SQLAlchemy INSERT statements omit them entirely, causing a
NotNullViolation on every source upsert.

This migration makes all six string/text extra columns nullable so that
ORM inserts succeed without having to know about them.  Numeric/boolean
extras are left alone (they are already nullable in the live schema).

The check is idempotent: columns that are already nullable are skipped.

Revision ID: c2d3e4f5a6b7
Revises: b1c3d4e5f6a7
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect, text

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Extra columns known to be present in production but absent from the ORM model.
# We only touch ones that could be NOT NULL — string/text columns that the ORM
# will never populate.
_COLUMNS_TO_MAKE_NULLABLE = [
    "url",
    "channel",
    "source_type",
    "error_reason",
    "language",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)

    existing = {
        c["name"]: c
        for c in inspector.get_columns("sources")
    }

    for col_name in _COLUMNS_TO_MAKE_NULLABLE:
        col_info = existing.get(col_name)
        if col_info is None:
            # Column doesn't exist in this environment — nothing to do.
            continue
        if col_info.get("nullable", True):
            # Already nullable — skip.
            continue

        # ALTER COLUMN … DROP NOT NULL
        op.alter_column("sources", col_name, nullable=True)


def downgrade() -> None:
    # Re-applying NOT NULL constraints without a guaranteed non-null value in
    # every row is unsafe, so downgrade is intentionally a no-op.
    pass

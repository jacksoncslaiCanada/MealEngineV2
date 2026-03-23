"""replace_sources_status_check

The production `sources` table has a pre-existing check constraint
``sources_status_check`` whose allowed values do not include ``'active'``.
Every SQLAlchemy INSERT fails with CheckViolation because the ORM inserts
rows with status='active'.

This migration drops the old constraint and creates a new one that covers
the four status values used by the Phase 1 application:
  candidate | active | paused | rejected

The upgrade is idempotent:
  - If the old constraint doesn't exist the DROP is skipped.
  - If the new constraint already exists the CREATE is skipped.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect, text

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT_NAME = "sources_status_check"
_VALID_STATUSES = ("candidate", "active", "paused", "rejected")


def _constraint_exists(bind, table: str, constraint: str) -> bool:
    result = bind.execute(
        text(
            """
            SELECT 1
            FROM   information_schema.table_constraints
            WHERE  table_name = :table
            AND    constraint_name = :constraint
            AND    constraint_type = 'CHECK'
            """
        ),
        {"table": table, "constraint": constraint},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    bind = op.get_bind()

    if _constraint_exists(bind, "sources", _CONSTRAINT_NAME):
        op.drop_constraint(_CONSTRAINT_NAME, "sources", type_="check")

    # Only add if still absent (e.g. already on a clean schema).
    if not _constraint_exists(bind, "sources", _CONSTRAINT_NAME):
        values = ", ".join(f"'{v}'" for v in _VALID_STATUSES)
        op.create_check_constraint(
            _CONSTRAINT_NAME,
            "sources",
            f"status IN ({values})",
        )


def downgrade() -> None:
    # Restoring the original unknown constraint definition is not possible,
    # so downgrade is a no-op.
    pass

#!/usr/bin/env python
"""One-time backfill: populate canonical_name for existing ingredient rows.

Any Ingredient row where canonical_name IS NULL gets normalise_ingredient()
applied to its ingredient_name and saved back.  Rows that already have a
canonical_name are left untouched.

Commits in batches of BATCH_SIZE to avoid holding a huge open transaction.

Usage
-----
    python scripts/backfill_canonical_names.py

    # Dry-run (prints what would change, no writes):
    python scripts/backfill_canonical_names.py --dry-run

Secrets required:
    DATABASE_URL — PostgreSQL connection string (env var or .env)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Ingredient
from app.db.session import SessionLocal
from app.normaliser import normalise_ingredient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def backfill(dry_run: bool = False) -> int:
    db = SessionLocal()
    try:
        total = db.query(Ingredient).filter(Ingredient.canonical_name.is_(None)).count()
        if total == 0:
            logger.info("Nothing to backfill — all rows already have canonical_name.")
            return 0

        logger.info("Found %d ingredient row(s) with canonical_name=NULL.", total)
        if dry_run:
            logger.info("Dry-run mode — sampling first %d rows:", min(10, total))

        updated = 0
        offset = 0

        while True:
            batch = (
                db.query(Ingredient)
                .filter(Ingredient.canonical_name.is_(None))
                .order_by(Ingredient.id)
                .limit(BATCH_SIZE)
                .all()
            )
            if not batch:
                break

            for row in batch:
                canonical = normalise_ingredient(row.ingredient_name)
                if dry_run:
                    if updated < 10:
                        print(f"  [{row.id}] {row.ingredient_name!r:40s} → {canonical!r}")
                else:
                    row.canonical_name = canonical
                updated += 1

            if not dry_run:
                db.commit()
                logger.info("  Committed batch — %d / %d done.", updated, total)

            offset += BATCH_SIZE
            if len(batch) < BATCH_SIZE:
                break

        if dry_run:
            if total > 10:
                print(f"  ... and {total - 10} more rows.")
            logger.info("Dry-run complete — %d row(s) would be updated.", updated)
        else:
            logger.info("Backfill complete — %d row(s) updated.", updated)

        return updated

    except Exception:
        logger.exception("Backfill failed.")
        db.rollback()
        return -1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing to the database.",
    )
    args = parser.parse_args()

    result = backfill(dry_run=args.dry_run)
    return 0 if result >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())

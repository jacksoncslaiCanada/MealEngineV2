#!/usr/bin/env python
"""CLI entry point for the weekly pipeline.

Usage
-----
    python scripts/run_pipeline.py

The script connects to the database configured via DATABASE_URL, runs the
four-step weekly pipeline (ingest → score → discover → promote), prints a
summary, and exits with code 0 on success or 1 if any step raised an error.

Secrets required (set as environment variables or in .env):
    DATABASE_URL      — PostgreSQL connection string
    YOUTUBE_API_KEY   — YouTube Data API v3 key
"""

import logging
import sys
from pathlib import Path

# Make sure the project root is on sys.path when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.pipeline import run_weekly_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def main() -> int:
    db = SessionLocal()
    try:
        report = run_weekly_pipeline(db)
        return 1 if report.errors else 0
    except Exception:
        logging.exception("Pipeline crashed with an unhandled exception")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

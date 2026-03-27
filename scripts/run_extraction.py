#!/usr/bin/env python
"""CLI entry point for the ingredient extraction step.

Finds all raw_recipe rows without ingredient rows and extracts structured
ingredients using Claude (claude-opus-4-6).

Usage
-----
    python scripts/run_extraction.py               # process all unprocessed
    python scripts/run_extraction.py --limit 50    # process at most 50 recipes

Secrets required (set as environment variables or in .env):
    DATABASE_URL        — PostgreSQL connection string
    ANTHROPIC_API_KEY   — Anthropic API key
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic

from app.config import settings
from app.db.session import SessionLocal
from app.extractor import extract_all_unprocessed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract ingredients from unprocessed recipes")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of recipes to process (default: all unprocessed)",
    )
    args = parser.parse_args()

    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is not configured — cannot run extraction")
        return 1

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    db = SessionLocal()
    try:
        rows = extract_all_unprocessed(db, client=client, limit=args.limit)
        logger.info("Extraction complete — %d ingredient row(s) written", len(rows))
        return 0
    except Exception:
        logger.exception("Extraction crashed with an unhandled exception")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

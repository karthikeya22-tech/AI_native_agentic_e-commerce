#!/usr/bin/env python3
"""
Generate embeddings for existing active products.

Uses the local BAAI/bge-small-en-v1.5 model (384 dims) via
sentence-transformers. No hosted API, no API key.

Safe to run repeatedly:
- Products that already have an embedding are skipped.
- Pass --rebuild to force regeneration of all active products.

Usage:
    python scripts/generate_product_embeddings.py [--batch-size 32] [--rebuild]
"""

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.embeddings.pipeline import generate_product_embeddings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate product embeddings locally (BAAI/bge-small-en-v1.5)."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of products embedded per batch (default: 32).",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate embeddings even if one already exists.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stats = generate_product_embeddings(
            db,
            batch_size=args.batch_size,
            rebuild=args.rebuild,
        )
    finally:
        db.close()

    logger.info("Embedding run complete: %s", stats.as_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())

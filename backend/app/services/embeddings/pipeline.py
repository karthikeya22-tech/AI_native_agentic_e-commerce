"""
Product embedding generation pipeline (local, batched).

Generates embeddings for ACTIVE products using the canonical text
formatter and stores them in `products.embedding`.

Safety properties:
- Only active products are processed.
- Products that already have an embedding are skipped unless
  `rebuild=True` is passed.
- Commits happen per batch, so interrupted runs leave the database in a
  consistent state and re-running the script simply resumes/skips.
- No schema changes, no LLM calls, no retrieval logic.

Vector similarity is a retrieval/ranking signal only. It must never be
used to bypass deterministic constraints such as merchant_id, budget,
price, inventory, is_active, or merchant policies.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.embeddings.model import (
    EMBEDDING_DIMENSION,
    get_embedding_model,
)
from app.services.embeddings.product_text import build_product_embedding_text

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 32


@dataclass
class EmbeddingRunStats:
    processed: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict:
        return {
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
        }


def generate_product_embeddings(
    db: Session,
    batch_size: int = DEFAULT_BATCH_SIZE,
    rebuild: bool = False,
    model=None,
) -> EmbeddingRunStats:
    """
    Generate embeddings for all active products.

    Args:
        db: SQLAlchemy session (SessionLocal or test session).
        batch_size: number of products embedded per model call/commit.
        rebuild: if True, regenerate embeddings even when one exists.
        model: optional pre-built embedding model (mainly for tests);
               defaults to the shared local BAAI/bge-small-en-v1.5 model.

    Returns:
        EmbeddingRunStats with processed/skipped/failed counts.
    """
    stats = EmbeddingRunStats()
    embedding_model = model if model is not None else get_embedding_model()

    from app.models.product import Product

    query = db.query(Product).filter(Product.is_active.is_(True))
    products = query.all()

    pending: list[Product] = []
    for product in products:
        if product.embedding is not None and not rebuild:
            stats.skipped += 1
            continue
        pending.append(product)

    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        texts = [build_product_embedding_text(product) for product in batch]
        try:
            vectors = embedding_model.encode(texts)
        except Exception:
            logger.exception("Embedding batch failed; skipping batch")
            stats.failed += len(batch)
            continue

        for product, vector in zip(batch, vectors):
            if len(vector) != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Expected {EMBEDDING_DIMENSION}-dim embedding, "
                    f"got {len(vector)}"
                )
            product.embedding = vector
            stats.processed += 1
        db.commit()

    return stats

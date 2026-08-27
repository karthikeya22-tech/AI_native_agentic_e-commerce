"""
Semantic product retrieval for buyer search (Phase 3B.2).

Given a structured buyer intent, retrieves the most relevant ACTIVE,
in-stock products for one merchant using pgvector cosine similarity over
the existing `products.embedding` column (BAAI/bge-small-en-v1.5, 384d).

Architecture rule enforced here:

Vector similarity is ONLY a ranking signal. The following deterministic
constraints are authoritative and are always applied as SQL-level filters
before ranking:

- merchant_id
- is_active
- inventory_quantity (> 0)
- budget_min / budget_max (on price)
- category

No product embeddings are generated here and no LLM is called.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.embeddings.model import get_embedding_model

DEFAULT_LIMIT = 5


def build_intent_query_text(intent) -> str:
    """
    Compose a deterministic semantic query text from a structured intent.

    Uses the same content style as the canonical product text so the query
    lands in the same embedding space as the stored product embeddings.
    """
    parts = []
    if intent.category:
        parts.append(f"category: {intent.category}")
    if intent.brand:
        parts.append(f"brand: {intent.brand}")
    if intent.use_case:
        parts.append(f"use case: {intent.use_case}")
    if intent.requirements:
        parts.append("requirements: " + ", ".join(intent.requirements))
    if intent.preferences:
        parts.append("preferences: " + ", ".join(intent.preferences))
    return ". ".join(parts)


def get_intent_embedding_model():
    """FastAPI dependency wrapping the shared local embedding model."""
    return get_embedding_model()


@dataclass
class SearchResult:
    product: Product
    similarity: float


def search_products_for_intent(
    db: Session,
    intent,
    model=None,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    """
    Retrieve up to `limit` products ranked by semantic similarity.

    Deterministic constraints are applied first (merchant, active, stock,
    budget, category); cosine distance ranks what survives those filters.

    Args:
        db: SQLAlchemy session.
        intent: structured intent (BuyerSearchRequest-like object).
        model: optional embedding model (mainly for tests); defaults to the
               shared local BAAI/bge-small-en-v1.5 model.
        limit: maximum number of results (default 5).

    Returns:
        List of SearchResult, most similar first.
    """
    embedding_model = model if model is not None else get_embedding_model()

    query_text = build_intent_query_text(intent)
    [query_vector] = embedding_model.encode([query_text])

    # --- Authoritative deterministic constraints ---------------------------
    criteria = [
        Product.merchant_id == intent.merchant_id,
        Product.is_active.is_(True),
        Product.inventory_quantity > 0,
        Product.embedding.isnot(None),
    ]
    if intent.category:
        from sqlalchemy import or_
        words = intent.category.split()
        if len(words) > 1:
            criteria.append(
                or_(*[Product.category.ilike(f"%{w}%") for w in words])
            )
        else:
            criteria.append(Product.category.ilike(f"%{intent.category}%"))
    if intent.budget_min is not None:
        criteria.append(Product.price >= intent.budget_min)
    if intent.budget_max is not None:
        criteria.append(Product.price <= intent.budget_max)

    # --- Ranking signal only ------------------------------------------------
    distance = Product.embedding.cosine_distance(query_vector)
    rows = (
        db.query(Product, distance.label("similarity"))
        .filter(*criteria)
        .order_by(distance.asc())
        .limit(limit)
        .all()
    )
    return [
        SearchResult(product=product, similarity=float(similarity))
        for product, similarity in rows
    ]

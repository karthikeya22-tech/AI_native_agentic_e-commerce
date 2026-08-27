from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import sql

from app.models.product import Product
from app.services.embeddings.model import EMBEDDING_DIMENSION
from app.services.embeddings.pipeline import generate_product_embeddings
from app.services.embeddings.product_text import build_product_embedding_text


def make_product(**overrides):
    defaults = {
        "id": uuid4(),
        "merchant_id": uuid4(),
        "name": "Wireless Noise Cancelling Headphones",
        "category": "Electronics",
        "description": "Over-ear headphones with active noise cancellation.",
        "price": 12999.00,
        "currency": "INR",
        "inventory_quantity": 42,
        "delivery_info": {"estimated_days": "3-5 days", "free_shipping": True},
        "return_policy": "7-day hassle-free returns.",
        "product_metadata": {"brand": "SoundCore", "battery_life_hours": 30},
        "is_active": True,
        "embedding": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeQuery:
    """Minimal SQLAlchemy Query stand-in that honours column filters."""

    def __init__(self, result):
        self.result = result

    def filter(self, *criteria):
        rows = self.result
        for crit in criteria:
            column = crit.left.key
            right = crit.right
            if isinstance(right, sql.elements.True_):
                value = True
            elif isinstance(right, sql.elements.False_):
                value = False
            else:
                value = right.value
            rows = [r for r in rows if getattr(r, column, None) == value]
        self.result = rows
        return self

    def all(self):
        return list(self.result)


class FakeSession:
    def __init__(self, products):
        self.products = products
        self.commit_count = 0

    def query(self, model):
        assert model is Product
        return FakeQuery(self.products)

    def commit(self):
        self.commit_count += 1


class FakeEmbeddingModel:
    """Deterministic mock encoder producing fixed-dimension vectors."""

    def __init__(self, dimension=EMBEDDING_DIMENSION):
        self.dimension = dimension
        self.texts = []
        self.call_count = 0

    def encode(self, texts):
        self.call_count += 1
        self.texts.extend(texts)
        return [[0.1] * self.dimension for _ in texts]


# ---------------------------------------------------------------------------
# Canonical text formatting
# ---------------------------------------------------------------------------


def test_canonical_text_includes_all_content_fields():
    product = make_product()
    text = build_product_embedding_text(product)

    assert product.name in text
    assert f"Category: {product.category}" in text
    assert product.description in text
    assert "Delivery:" in text
    assert "estimated days: 3-5 days" in text
    assert "Return policy:" in text
    assert product.return_policy in text
    assert "Specifications:" in text
    assert "brand: SoundCore" in text
    assert "battery life hours: 30" in text


def test_canonical_text_excludes_inventory_price_and_policies():
    product = make_product()
    text = build_product_embedding_text(product)

    assert str(product.inventory_quantity) not in text
    assert "inventory" not in text.lower()
    assert str(product.price) not in text
    assert product.currency not in text


def test_canonical_text_handles_missing_optional_fields():
    product = make_product(
        delivery_info=None,
        return_policy=None,
        product_metadata=None,
    )
    text = build_product_embedding_text(product)

    assert product.name in text
    assert "Delivery" not in text
    assert "Return policy" not in text
    assert "Specifications" not in text


# ---------------------------------------------------------------------------
# Embedding generation pipeline (mocked model)
# ---------------------------------------------------------------------------


def test_embedding_dimension_is_384():
    assert EMBEDDING_DIMENSION == 384
    session = FakeSession([make_product()])
    model = FakeEmbeddingModel()

    generate_product_embeddings(session, model=model)

    stored = session.products[0].embedding
    assert stored == [0.1] * 384
    assert len(stored) == 384


def test_pipeline_rejects_wrong_dimension():
    session = FakeSession([make_product()])
    model = FakeEmbeddingModel(dimension=128)

    with pytest.raises(ValueError):
        generate_product_embeddings(session, model=model)


def test_existing_embeddings_are_skipped():
    already_embedded = make_product(embedding=[0.5] * 384)
    fresh = make_product()
    session = FakeSession([already_embedded, fresh])
    model = FakeEmbeddingModel()

    stats = generate_product_embeddings(session, model=model)

    assert len(model.texts) == 1
    assert stats.skipped == 1
    assert stats.processed == 1
    assert stats.failed == 0
    assert already_embedded.embedding == [0.5] * 384
    assert len(fresh.embedding) == 384


def test_rebuild_flag_regenerates_existing_embeddings():
    already_embedded = make_product(embedding=[0.5] * 384)
    session = FakeSession([already_embedded])
    model = FakeEmbeddingModel()

    stats = generate_product_embeddings(session, rebuild=True, model=model)

    assert stats.skipped == 0
    assert stats.processed == 1
    assert already_embedded.embedding == [0.1] * 384


def test_inactive_products_are_not_processed():
    active = make_product()
    inactive = make_product(is_active=False)
    session = FakeSession([active, inactive])
    model = FakeEmbeddingModel()

    stats = generate_product_embeddings(session, model=model)

    assert stats.skipped == 0
    assert stats.processed == 1
    assert session.products[0].embedding is not None
    assert inactive.embedding is None


def test_batches_commit_per_batch():
    products = [make_product() for _ in range(5)]
    session = FakeSession(products)
    model = FakeEmbeddingModel()

    generate_product_embeddings(session, batch_size=2, model=model)

    assert stats_processed(model) == 5
    # ceil(5 / 2) = 3 commits
    assert session.commit_count == 3


def stats_processed(model: FakeEmbeddingModel) -> int:
    return len(model.texts)

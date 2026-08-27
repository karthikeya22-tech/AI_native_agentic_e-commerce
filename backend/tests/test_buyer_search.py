"""Focused tests for Phase 3B.2 semantic product retrieval."""

import math
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.db.session import get_db
from app.main import app
from app.services.retrieval.product_search import get_intent_embedding_model


URL = "/api/v1/buyer/search"

MERCHANT_ID = uuid4()
OTHER_MERCHANT_ID = uuid4()
DIM = 384


class FakeMerchant:
    """Minimal stand-in for Merchant ORM model."""

    def __init__(self, id_val):
        self.id = id_val


def unit_vector(first: float = 1.0, second: float = 0.0) -> list[float]:
    """Return a normalized vector padded to 384 dimensions."""
    norm = math.sqrt(first * first + second * second)

    vec = [0.0] * DIM
    vec[0] = first / norm
    vec[1] = second / norm

    return vec


def make_product(
    merchant_id=MERCHANT_ID,
    name="AI Dev Laptop",
    category="laptop",
    price=Decimal("65000.00"),
    inventory_quantity=10,
    is_active=True,
    embedding=None,
):
    if embedding is None:
        embedding = unit_vector(1.0, 0.0)

    return type(
        "FakeProduct",
        (),
        {
            "id": uuid4(),
            "merchant_id": merchant_id,
            "name": name,
            "description": f"{name} description",
            "category": category,
            "price": price,
            "currency": "INR",
            "inventory_quantity": inventory_quantity,
            "is_active": is_active,
            "embedding": embedding,
        },
    )()


class FakeQuery:
    """Minimal query object for testing retrieval behavior."""

    def __init__(self, result, query_vector=None):
        self.result = list(result)
        self.filters = []
        self.orderings = []
        self._limit = None
        self.query_vector = query_vector
        self.returns_pairs = False

    @staticmethod
    def _bound_value(expression):
        """Extract a normal Python value from SQLAlchemy expressions."""

        if expression is None:
            return None

        if isinstance(expression, sql.elements.Null):
            return None

        if isinstance(expression, sql.elements.True_):
            return True

        if isinstance(expression, sql.elements.False_):
            return False

        if hasattr(expression, "value"):
            return expression.value

        return expression

    def filter(self, *criteria):
        self.filters.extend(criteria)

        rows = list(self.result)

        for criterion in criteria:
            left_key = criterion.left.key
            expression_text = str(criterion).strip().lower()

            # -------------------------------------------------------------
            # Explicit SQL identity/null checks.
            # -------------------------------------------------------------

            if " is not null" in expression_text:
                rows = [
                    row
                    for row in rows
                    if getattr(row, left_key) is not None
                ]
                continue

            if " is null" in expression_text:
                rows = [
                    row
                    for row in rows
                    if getattr(row, left_key) is None
                ]
                continue

            if " is true" in expression_text:
                rows = [
                    row
                    for row in rows
                    if getattr(row, left_key) is True
                ]
                continue

            if " is false" in expression_text:
                rows = [
                    row
                    for row in rows
                    if getattr(row, left_key) is False
                ]
                continue

            # -------------------------------------------------------------
            # Normal SQLAlchemy comparisons:
            # =, !=, <, <=, >, >=
            # -------------------------------------------------------------

            right_value = self._bound_value(criterion.right)

            op_name = getattr(criterion.operator, "__name__", "")

            if op_name == "ilike_op":
                pattern = str(right_value).replace("%", "")
                rows = [
                    row
                    for row in rows
                    if pattern.lower() in str(getattr(row, left_key, "")).lower()
                ]
            else:
                rows = [
                    row
                    for row in rows
                    if criterion.operator(
                        getattr(row, left_key),
                        right_value,
                    )
                ]

        self.result = rows
        return self

    def order_by(self, *criteria):
        self.orderings.extend(criteria)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _similarity(self, product_embedding):
        if self.query_vector is None:
            raise AssertionError(
                "query_vector must be provided for similarity tests"
            )

        dot = sum(
            a * b
            for a, b in zip(
                product_embedding,
                self.query_vector,
            )
        )

        norm_a = math.sqrt(
            sum(value * value for value in product_embedding)
        )

        norm_b = math.sqrt(
            sum(value * value for value in self.query_vector)
        )

        return dot / (norm_a * norm_b)

    def all(self):
        rows = list(self.result)

        if self.returns_pairs and self.query_vector is not None:
            ranked = [
                (
                    row,
                    self._similarity(row.embedding),
                )
                for row in rows
            ]

            # Production query:
            # cosine_distance ASC
            #
            # Equivalent ranking:
            # similarity DESC
            ranked.sort(
                key=lambda pair: pair[1],
                reverse=True,
            )

            if self._limit is not None:
                ranked = ranked[: self._limit]

            return ranked

        if self._limit is not None:
            rows = rows[: self._limit]

        return rows

    def first(self):
        return self.result[0] if self.result else None


class FakeDB:
    """Minimal database stand-in for API tests."""

    def __init__(
        self,
        merchants=None,
        products=None,
        query_vector=None,
    ):
        self.merchant_query = FakeQuery(
            merchants or []
        )

        self.product_query = FakeQuery(
            products or [],
            query_vector=query_vector,
        )

    def query(self, *entities):
        if entities[0].__name__ == "Merchant":
            return self.merchant_query

        self.product_query.returns_pairs = len(entities) > 1
        return self.product_query


class FakeEmbeddingModel:
    """Deterministic embedding model for tests."""

    def __init__(self):
        self.texts = []

    def encode(self, texts):
        self.texts.extend(texts)

        return [
            unit_vector(1.0, 0.0)
            for _ in texts
        ]


def override(fake_db, fake_model=None):
    app.dependency_overrides[get_db] = lambda: fake_db

    app.dependency_overrides[get_intent_embedding_model] = (
        lambda: (
            fake_model
            if fake_model is not None
            else FakeEmbeddingModel()
        )
    )


client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def search_payload(**overrides):
    payload = {
        "merchant_id": str(MERCHANT_ID),
        "category": "laptop",
        "budget_min": None,
        "budget_max": 70000,
        "use_case": "local AI development",
        "requirements": ["16GB RAM"],
        "preferences": [],
        "brand": None,
    }

    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. Relevant products
# ---------------------------------------------------------------------------


def test_relevant_products_are_returned():
    model = FakeEmbeddingModel()

    products = [
        make_product(name="AI Dev Laptop"),
        make_product(name="Coding Ultrabook"),
    ]

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=products,
            query_vector=unit_vector(1.0, 0.0),
        ),
        model,
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body["results"]) == 2

    names = {
        result["name"]
        for result in body["results"]
    }

    assert names == {
        "AI Dev Laptop",
        "Coding Ultrabook",
    }

    item = body["results"][0]

    assert set(item.keys()) == {
        "product_id",
        "name",
        "description",
        "category",
        "price",
        "currency",
        "inventory_quantity",
        "similarity",
    }

    assert item["category"] == "laptop"
    assert item["currency"] == "INR"
    assert item["inventory_quantity"] == 10
    assert item["price"] == "65000.00"
    assert 0.0 <= item["similarity"] <= 1.0

    assert len(model.texts) == 1

    query_text = model.texts[0]

    assert "laptop" in query_text
    assert "local AI development" in query_text
    assert "16GB RAM" in query_text


def test_results_ranked_by_similarity():
    close = make_product(
        name="Close Match",
        embedding=unit_vector(1.0, 0.05),
    )

    far = make_product(
        name="Far Match",
        embedding=unit_vector(0.05, 1.0),
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[far, close],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    results = response.json()["results"]

    assert results[0]["name"] == "Close Match"
    assert results[1]["name"] == "Far Match"
    assert results[0]["similarity"] > results[1]["similarity"]


# ---------------------------------------------------------------------------
# 2. Merchant isolation
# ---------------------------------------------------------------------------


def test_products_from_other_merchant_excluded():
    mine = make_product(name="Mine")

    theirs = make_product(
        merchant_id=OTHER_MERCHANT_ID,
        name="Theirs",
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[mine, theirs],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Mine"}


# ---------------------------------------------------------------------------
# 3. Budget filtering
# ---------------------------------------------------------------------------


def test_products_above_budget_max_excluded():
    affordable = make_product(
        name="Affordable",
        price=Decimal("60000.00"),
    )

    too_expensive = make_product(
        name="Too Expensive",
        price=Decimal("80000.00"),
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[
                affordable,
                too_expensive,
            ],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Affordable"}


def test_products_below_budget_min_excluded():
    cheap = make_product(
        name="Cheap",
        price=Decimal("10000.00"),
    )

    mid = make_product(
        name="Mid",
        price=Decimal("40000.00"),
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[cheap, mid],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(
            budget_min=30000,
            budget_max=None,
        ),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Mid"}


def test_budget_filters_present_in_query():
    fake_db = FakeDB(
        merchants=[FakeMerchant(MERCHANT_ID)],
        products=[],
        query_vector=unit_vector(1.0, 0.0),
    )

    override(fake_db)

    client.post(
        URL,
        json=search_payload(
            budget_min=30000,
            budget_max=70000,
        ),
    )

    filter_sql = " AND ".join(
        str(condition)
        for condition in fake_db.product_query.filters
    )

    assert "price" in filter_sql
    assert ">=" in filter_sql
    assert "<=" in filter_sql


# ---------------------------------------------------------------------------
# 4. Inventory
# ---------------------------------------------------------------------------


def test_out_of_stock_products_excluded():
    stocked = make_product(
        name="Stocked",
        inventory_quantity=5,
    )

    sold_out = make_product(
        name="Sold Out",
        inventory_quantity=0,
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[stocked, sold_out],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Stocked"}


# ---------------------------------------------------------------------------
# 5. Category
# ---------------------------------------------------------------------------


def test_category_filtering():
    laptop = make_product(
        name="Laptop",
        category="laptop",
    )

    phone = make_product(
        name="Phone",
        category="phone",
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[laptop, phone],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(category="laptop"),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Laptop"}


def test_no_category_means_no_category_filter():
    fake_db = FakeDB(
        merchants=[FakeMerchant(MERCHANT_ID)],
        products=[],
        query_vector=unit_vector(1.0, 0.0),
    )

    override(fake_db)

    client.post(
        URL,
        json=search_payload(category=None),
    )

    filter_sql = " AND ".join(
        str(condition)
        for condition in fake_db.product_query.filters
    )

    assert "category" not in filter_sql


# ---------------------------------------------------------------------------
# 6. Empty / inactive
# ---------------------------------------------------------------------------


def test_empty_result_set_handled_cleanly():
    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": []
    }


def test_inactive_products_excluded():
    active = make_product(
        name="Active",
        is_active=True,
    )

    inactive = make_product(
        name="Inactive",
        is_active=False,
    )

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[active, inactive],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200

    names = {
        result["name"]
        for result in response.json()["results"]
    }

    assert names == {"Active"}


# ---------------------------------------------------------------------------
# 7. Unknown merchant
# ---------------------------------------------------------------------------


def test_unknown_merchant_returns_404():
    override(
        FakeDB(
            merchants=[],
            products=[make_product()],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


# ---------------------------------------------------------------------------
# 8. Top-5 limit
# ---------------------------------------------------------------------------


def test_only_top_five_returned():
    products = [
        make_product(name=f"P{i}")
        for i in range(7)
    ]

    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=products,
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(),
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 5


# ---------------------------------------------------------------------------
# 9. Invalid budget range
# ---------------------------------------------------------------------------


def test_invalid_budget_range_rejected():
    override(
        FakeDB(
            merchants=[FakeMerchant(MERCHANT_ID)],
            products=[],
            query_vector=unit_vector(1.0, 0.0),
        )
    )

    response = client.post(
        URL,
        json=search_payload(
            budget_min=70000,
            budget_max=30000,
        ),
    )

    assert response.status_code == 422
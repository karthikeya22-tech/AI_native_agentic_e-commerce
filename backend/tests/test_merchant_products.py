from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product

MERCHANT_ID = uuid4()


class FakeQuery:
    """Stands in for a SQLAlchemy Query, recording filters and orderings."""

    def __init__(self, result):
        self.result = result
        self.filters = []
        self.orderings = []
        self._mode = "all"

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def order_by(self, *criteria):
        self.orderings.extend(criteria)
        return self

    def first(self):
        return self.result[0] if self.result else None

    def all(self):
        rows = self.result
        for crit in self.filters:
            column = crit.left.key
            right = crit.right
            if isinstance(right, sql.elements.True_):
                value = True
            elif isinstance(right, sql.elements.False_):
                value = False
            else:
                value = right.value
            rows = [r for r in rows if getattr(r, column) == value]
        return rows


class FakeDB:
    """Routes .query(Model) calls to canned FakeQuery results."""

    def __init__(self, merchant_result=None, product_results=None):
        self.merchant_query = FakeQuery(merchant_result or [])
        self.product_query = FakeQuery(product_results or [])
        self.queries = {
            Merchant: self.merchant_query,
            Product: self.product_query,
        }
        self.added = []
        self.committed = False
        self.rolled_back = False

    def query(self, model):
        return self.queries[model]

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


def make_product(is_active=True, name="Wireless Mouse"):
    return type(
        "FakeProduct",
        (),
        {
            "id": uuid4(),
            "merchant_id": MERCHANT_ID,
            "name": name,
            "description": "An ergonomic wireless mouse",
            "category": "electronics",
            "price": Decimal("1299.00"),
            "currency": "INR",
            "inventory_quantity": 42,
            "delivery_info": {"eta_days": 3, "free_shipping": True},
            "return_policy": "7-day returns",
            "is_active": is_active,
            "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        },
    )()


def override_db(fake_db):
    app.dependency_overrides[get_db] = lambda: fake_db


client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_list_products_success():
    products = [make_product(), make_product(name="USB-C Cable")]
    override_db(FakeDB(merchant_result=[object()], product_results=products))

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/products")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    item = body[0]
    assert item["name"] == "Wireless Mouse"
    assert item["category"] == "electronics"
    assert item["currency"] == "INR"
    assert Decimal(item["price"]) == Decimal("1299.00")
    assert item["inventory_quantity"] == 42
    assert item["delivery_info"] == {"eta_days": 3, "free_shipping": True}
    assert item["return_policy"] == "7-day returns"
    assert item["is_active"] is True
    assert item["created_at"] == "2026-08-01T00:00:00Z"
    assert set(item.keys()) == {
        "id",
        "name",
        "description",
        "category",
        "price",
        "currency",
        "inventory_quantity",
        "delivery_info",
        "return_policy",
        "is_active",
        "created_at",
    }


def test_unknown_merchant_returns_404():
    override_db(FakeDB(merchant_result=[], product_results=[make_product()]))

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/products")

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_inactive_products_excluded():
    products = [
        make_product(is_active=True),
        make_product(is_active=False, name="Discontinued Item"),
    ]
    fake_db = FakeDB(merchant_result=[object()], product_results=products)
    override_db(fake_db)

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/products")

    assert response.status_code == 200
    body = response.json()
    assert all(item["is_active"] for item in body)

    # The active-only filter must be part of the SQL criteria.
    filter_sql = " AND ".join(str(c) for c in fake_db.product_query.filters)
    assert "is_active" in filter_sql
    assert "true" in filter_sql.lower()

    # Newest first ordering must be applied.
    order_sql = ", ".join(str(c) for c in fake_db.product_query.orderings)
    assert "created_at" in order_sql
    assert "desc" in order_sql.lower()

    # Pydantic serialization drops the inactive product even though the fake
    # query returned it, proving the API layer honours the active-only contract.
    assert all(item["name"] != "Discontinued Item" for item in body)


PRODUCT_PAYLOAD = {
    "name": "Wireless Mouse",
    "description": "An ergonomic wireless mouse",
    "category": "electronics",
    "price": "1299.00",
    "currency": "INR",
    "inventory_quantity": 42,
    "delivery_info": {"eta_days": 3, "free_shipping": True},
    "return_policy": "7-day returns",
}


def test_create_product_success():
    fake_db = FakeDB(merchant_result=[object()])
    override_db(fake_db)

    response = client.post(
        f"/api/v1/merchants/{MERCHANT_ID}/products", json=PRODUCT_PAYLOAD
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["name"] == PRODUCT_PAYLOAD["name"]
    assert body["description"] == PRODUCT_PAYLOAD["description"]
    assert body["category"] == PRODUCT_PAYLOAD["category"]
    assert Decimal(body["price"]) == Decimal("1299.00")
    assert body["currency"] == "INR"
    assert body["inventory_quantity"] == 42
    assert body["delivery_info"] == {"eta_days": 3, "free_shipping": True}
    assert body["return_policy"] == "7-day returns"
    assert body["is_active"] is True
    assert body["created_at"]

    assert fake_db.committed is True
    assert len(fake_db.added) == 1
    created = fake_db.added[0]
    assert isinstance(created, Product)
    assert created.merchant_id == MERCHANT_ID
    assert created.is_active is True


def test_create_product_unknown_merchant_returns_404():
    override_db(FakeDB(merchant_result=[]))

    response = client.post(
        f"/api/v1/merchants/{MERCHANT_ID}/products", json=PRODUCT_PAYLOAD
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_create_product_negative_price_rejected():
    payload = {**PRODUCT_PAYLOAD, "price": "-1.00"}

    response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/products", json=payload)

    assert response.status_code == 422


def test_create_product_negative_inventory_rejected():
    payload = {**PRODUCT_PAYLOAD, "inventory_quantity": -5}

    response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/products", json=payload)

    assert response.status_code == 422

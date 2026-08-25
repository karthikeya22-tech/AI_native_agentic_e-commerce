from types import SimpleNamespace
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.api.v1.readiness_service import analyze_readiness, evaluate_product
from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product

MERCHANT_ID = uuid4()

client = TestClient(app)


class FakeDB:
    """Minimal stand-in for a SQLAlchemy Session."""

    def __init__(self, merchant_result=None, product_results=None):
        self._results = {
            Merchant: merchant_result or [],
            Product: product_results or [],
        }

    def query(self, model):
        return _FakeQuery(self._results[model])


class _FakeQuery:
    def __init__(self, result):
        self.result = result
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def first(self):
        rows = self._filtered()
        return rows[0] if rows else None

    def all(self):
        return self._filtered()

    def _filtered(self):
        rows = self.result
        for crit in self.criteria:
            column = crit.left.key
            right = crit.right
            if isinstance(right, sql.elements.True_):
                value = True
            elif isinstance(right, sql.elements.False_):
                value = False
            else:
                value = right.value
            rows = [
                r for r in rows if getattr(r, column, None) == value
            ]
        return rows


def make_product(**overrides) -> object:
    base = dict(
        id=uuid4(),
        merchant_id=MERCHANT_ID,
        name="Complete Widget",
        description="A fully specified widget with plenty of descriptive detail.",
        category="electronics",
        price=Decimal("999.00"),
        currency="INR",
        inventory_quantity=10,
        delivery_info={"eta_days": 3},
        return_policy="7-day returns",
        product_metadata={"brand": "TechKart"},
        is_active=True,
    )
    base.update(overrides)
    return type("FakeProduct", (), base)()


def override_db(fake_db: FakeDB) -> None:
    app.dependency_overrides[get_db] = lambda: fake_db


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_complete_products_score_100():
    products = [make_product(), make_product()]

    score, analyzed, issues = analyze_readiness(products)

    assert score == 100
    assert analyzed == 2
    assert issues == []


def test_incomplete_products_produce_issues_and_lower_score():
    products = [
        make_product(),
        make_product(
            name="Bare Bones Item",
            description="Short.",
            category=None,
            price=Decimal("0.00"),
            inventory_quantity=-1,
            delivery_info={},
            return_policy="",
            product_metadata=None,
        ),
    ]

    score, analyzed, issues = analyze_readiness(products)

    # First product is perfect (100); second loses 25/2 + 10 + 20 + 10 + 10 + 10 + 15.
    assert analyzed == 2
    assert score == round((100 + 100 - 12 - 10 - 20 - 10 - 10 - 10 - 15) / 2)
    issue_types = {i["issue_type"] for i in issues}
    assert issue_types == {
        "short_description",
        "missing_category",
        "invalid_price",
        "invalid_inventory",
        "missing_delivery_info",
        "missing_return_policy",
        "missing_metadata",
    }
    severities = {
        i["issue_type"]: i["severity"]
        for i in issues
        if i["product_name"] == "Bare Bones Item"
    }
    assert severities["short_description"] == "medium"
    assert severities["invalid_price"] == "high"
    assert severities["missing_metadata"] == "low"


def test_scoring_is_deterministic():
    products = [make_product(description="", product_metadata=None)]

    results = [analyze_readiness(products) for _ in range(5)]

    assert all(r == results[0] for r in results)
    score, _, _ = results[0]
    # Missing description (-25) and missing metadata (-15).
    assert score == 60


def test_missing_description_scores_zero_for_that_criterion():
    product = make_product(description="")
    score, issues = evaluate_product(product)
    types = {i["issue_type"] for i in issues}

    assert score == 75
    assert "missing_description" in types


def test_unknown_merchant_returns_404():
    override_db(FakeDB(merchant_result=[]))

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/readiness")

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_no_active_products_returns_zero_score():
    override_db(FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=[]))

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert body["overall_score"] == 0
    assert body["products_analyzed"] == 0
    assert body["issues_count"] == 0
    assert body["issues"] == []


def test_readiness_endpoint_with_mixed_catalog():
    products = [
        make_product(),
        make_product(
            name="No Metadata Item",
            product_metadata=None,
        ),
        make_product(is_active=False, description="", product_metadata=None),
    ]
    override_db(FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products))

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    # Inactive product must not be analyzed.
    assert body["products_analyzed"] == 2
    # Perfect product (100) + one missing only metadata (85).
    assert body["overall_score"] == round((100 + 85) / 2)
    assert body["issues_count"] == 1
    issue = body["issues"][0]
    assert set(issue.keys()) == {
        "product_id",
        "product_name",
        "issue_type",
        "description",
        "severity",
        "suggested_action",
    }
    assert issue["issue_type"] == "missing_metadata"


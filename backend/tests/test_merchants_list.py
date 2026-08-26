from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant, MerchantStatus

MERCHANT_ID = uuid4()

client = TestClient(app)


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def all(self):
        rows = self.result
        for crit in self.criteria:
            column = crit.left.key
            right = crit.right
            if isinstance(right, sql.elements.True_):
                value = True
            elif isinstance(right, sql.elements.False_):
                value = False
            else:
                value = getattr(right, "value", right)
            rows = [r for r in rows if getattr(r, column, None) == value]
        return rows


class FakeDB:
    def __init__(self, merchants):
        self.merchants = merchants

    def query(self, model):
        return FakeQuery(self.merchants)


def make_merchant(status=MerchantStatus.ACTIVE) -> SimpleNamespace:
    return SimpleNamespace(
        id=MERCHANT_ID,
        name="TechKart",
        category="Electronics",
        description="Everyday tech.",
        status=status,
    )


def override_db(db):
    app.dependency_overrides[get_db] = lambda: db


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_list_merchants_returns_active_only():
    override_db(
        FakeDB(
            [
                make_merchant(),
                make_merchant(status=MerchantStatus.INACTIVE),
            ]
        )
    )

    response = client.get("/api/v1/merchants")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    merchant = body[0]
    assert merchant["id"] == str(MERCHANT_ID)
    assert set(merchant.keys()) == {
        "id",
        "name",
        "category",
        "description",
        "status",
    }
    assert merchant["status"] == "active"


def test_list_merchants_empty():
    override_db(FakeDB([]))

    response = client.get("/api/v1/merchants")

    assert response.status_code == 200
    assert response.json() == []

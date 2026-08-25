import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.ai.provider import (
    LLMConfigurationError,
    LLMProvider,
    LLMRequestError,
)
from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product
from decimal import Decimal

MERCHANT_ID = uuid4()

client = TestClient(app)

VALID_LLM_RESPONSE = {
    "recommendations": [
        {
            "title": "Add delivery information",
            "explanation": "AI buyers cannot evaluate shipping speed without it.",
            "suggested_action": "Add estimated delivery days to the product.",
            "expected_impact": "Better AI discoverability and conversion.",
            "priority": "high",
        }
    ]
}


class FakeDB:
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
            rows = [r for r in rows if getattr(r, column, None) == value]
        return rows


def make_product(**overrides) -> object:
    base = dict(
        id=uuid4(),
        merchant_id=MERCHANT_ID,
        name="Bare Widget",
        description="Short.",
        category="electronics",
        price=Decimal("499.00"),
        currency="INR",
        inventory_quantity=5,
        delivery_info=None,
        return_policy="",
        product_metadata={"brand": "TechKart"},
        is_active=True,
    )
    base.update(overrides)
    return type("FakeProduct", (), base)()


def override_db_and_llm(fake_db, provider) -> None:
    app.dependency_overrides[get_db] = lambda: fake_db
    from app.ai.provider import get_llm_provider as _get

    app.dependency_overrides[_get] = lambda: provider


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


class RecordingProvider(LLMProvider):
    """Mock LLM that records prompts and returns a canned response."""

    def __init__(self, response):
        self.response = response
        self.system_prompt = None
        self.user_prompt = None
        self.call_count = 0

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.call_count += 1
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response)


def test_successful_recommendation_generation():
    products = [make_product(), make_product(delivery_info={"eta_days": 2})]
    override_db_and_llm(
        FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products),
        RecordingProvider(VALID_LLM_RESPONSE),
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert len(body["recommendations"]) >= 1
    rec = body["recommendations"][0]
    assert set(rec.keys()) == {
        "title",
        "explanation",
        "suggested_action",
        "expected_impact",
        "priority",
    }
    assert rec["priority"] in {"low", "medium", "high"}


def test_merchant_not_found():
    override_db_and_llm(
        FakeDB(merchant_result=[]),
        RecordingProvider(VALID_LLM_RESPONSE),
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


def test_llm_failure_handled_gracefully():
    products = [make_product()]
    override_db_and_llm(
        FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products),
        RecordingProvider(LLMRequestError("boom")),
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_llm_configuration_error_handled():
    products = [make_product()]
    override_db_and_llm(
        FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products),
        RecordingProvider(LLMConfigurationError("no key")),
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 503


def test_supplied_issues_preserved_in_prompt():
    products = [
        make_product(),
        make_product(name="Second Item", product_metadata=None),
    ]
    provider = RecordingProvider(
        {"recommendations": [VALID_LLM_RESPONSE["recommendations"][0]] * 2}
    )
    override_db_and_llm(
        FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products),
        provider,
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 200

    # The prompt must contain the actual issue data.
    prompt_data = json.loads(provider.user_prompt)
    issue_types = {i["issue_type"] for i in prompt_data["readiness_issues"]}
    product_names = {i["product_name"] for i in prompt_data["readiness_issues"]}

    assert "missing_delivery_info" in issue_types
    assert "missing_return_policy" in issue_types
    assert "missing_metadata" in issue_types
    assert {"Bare Widget", "Second Item"} <= product_names
    # Severity must be passed through untouched.
    assert all(i["severity"] in {"low", "medium", "high"} for i in prompt_data["readiness_issues"])
    assert provider.call_count == 1


def test_no_issues_returns_empty_recommendations_without_llm_call():
    products = []  # no active products -> no issues
    provider = RecordingProvider(VALID_LLM_RESPONSE)
    override_db_and_llm(
        FakeDB(merchant_result=[SimpleNamespace(id=MERCHANT_ID)], product_results=products),
        provider,
    )

    response = client.get(f"/api/v1/merchants/{MERCHANT_ID}/growth-recommendations")

    assert response.status_code == 200
    assert response.json()["recommendations"] == []
    assert provider.call_count == 0


def test_recommendations_limited_to_supplied_issues():
    from app.ai.growth_service import generate_recommendations

    issues = [{"issue_type": "a", "product_name": "p"}]
    greedy_response = json.dumps(
        {
            "recommendations": [
                {
                    "title": f"rec {i}",
                    "explanation": "e",
                    "suggested_action": "s",
                    "expected_impact": "i",
                    "priority": "high",
                }
                for i in range(10)
            ]
        }
    )

    recs = generate_recommendations(issues, RecordingProvider(greedy_response))

    assert len(recs) == 1

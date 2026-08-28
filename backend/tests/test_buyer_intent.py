import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.ai.provider import (
    LLMProvider,
    LLMRequestError,
    get_llm_provider,
)
from app.main import app

client = TestClient(app)

URL = "/api/v1/buyer/intent"


class MockProvider(LLMProvider):
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


def override_provider(provider) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: provider


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_successful_intent_extraction():
    provider = MockProvider(
        {
            "category": "laptop",
            "budget_min": None,
            "budget_max": 70000,
            "use_case": "local AI development",
            "requirements": ["16GB RAM"],
            "preferences": [],
            "brand": None,
        }
    )
    override_provider(provider)

    response = client.post(
        URL, json={"message": "I need a laptop for local AI development under ₹70,000 with 16GB RAM."}
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "category": "laptop",
        "budget_min": None,
        "budget_max": 70000.0,
        "use_case": "local AI development",
        "requirements": ["16GB RAM"],
        "preferences": [],
        "brand": None,
        "intent_source": "llm",
    }
    assert provider.call_count == 1


def test_buyer_message_is_passed_to_llm():
    provider = MockProvider(
        {"category": "phone", "budget_max": "30,000", "budget_min": None}
    )
    override_provider(provider)

    client.post(URL, json={"message": "Looking for a phone under ₹30,000"})

    prompt_data = json.loads(provider.user_prompt)
    assert prompt_data["buyer_message"] == "Looking for a phone under ₹30,000"


def test_budget_string_is_normalized_to_number():
    provider = MockProvider(
        {"category": "phone", "budget_max": "₹70,000", "budget_min": None}
    )
    override_provider(provider)

    response = client.post(
        URL, json={"message": "phone under 70000"}
    )

    assert response.status_code == 200
    assert response.json()["budget_max"] == 70000.0


def test_unknown_fields_are_null_or_empty():
    provider = MockProvider({"category": "smartwatch"})
    override_provider(provider)

    response = client.post(URL, json={"message": "I want a smartwatch"})

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "smartwatch"
    assert body["budget_min"] is None
    assert body["budget_max"] is None
    assert body["use_case"] is None
    assert body["requirements"] == []
    assert body["preferences"] == []
    assert body["brand"] is None


def test_malformed_json_handled_gracefully():
    override_provider(MockProvider("not-json at all {"))

    response = client.post(URL, json={"message": "a laptop"})

    assert response.status_code == 502
    assert "unusable" in response.json()["detail"]


def test_schema_violation_handled_gracefully():
    # requirements as a plain string violates the list schema.
    override_provider(MockProvider({"category": "laptop", "requirements": "16GB"}))

    response = client.post(URL, json={"message": "laptop with 16GB"})

    assert response.status_code == 502


def test_llm_failure_returns_503():
    override_provider(MockProvider(LLMRequestError("boom")))

    response = client.post(URL, json={"message": "a laptop"})

    assert response.status_code == 503


def test_empty_message_rejected_without_llm_call():
    provider = MockProvider({})
    override_provider(provider)

    response = client.post(URL, json={"message": "   "})

    assert response.status_code == 422
    assert provider.call_count == 0

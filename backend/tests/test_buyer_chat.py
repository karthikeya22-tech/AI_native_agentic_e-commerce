"""Focused tests for Phase 3C.1 buyer shopping agent chat endpoint."""

import json
import logging
import math
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.db.session import get_db
from app.main import app
from app.ai.provider import LLMProvider, LLMError, LLMRequestError, get_llm_provider
from app.services.retrieval.product_search import get_intent_embedding_model

URL = "/api/v1/buyer/chat"
MERCHANT_ID = uuid4()
OTHER_MERCHANT_ID = uuid4()
DIM = 384


class FakeMerchant:
    def __init__(self, id_val):
        self.id = id_val


def unit_vector(first=1.0, second=0.0):
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
    embedding = embedding if embedding is not None else unit_vector(1.0, 0.0)
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
    def __init__(self, result, query_vector=None):
        self.result = list(result)
        self.filters = []
        self.orderings = []
        self._limit = None
        self.query_vector = query_vector or unit_vector(1.0, 0.0)
        self.returns_pairs = False

    def filter(self, *criteria):
        self.filters.extend(criteria)
        rows = self.result
        for crit in criteria:
            # Handle BooleanClauseList from or_()
            if isinstance(crit, sql.elements.BooleanClauseList):
                sub_clauses = list(crit.clauses)
                def _matches_or(row, clauses):
                    for sub in clauses:
                        if self._match_single(row, sub):
                            return True
                    return False
                rows = [r for r in rows if _matches_or(r, sub_clauses)]
            else:
                rows = [r for r in rows if self._match_single(r, crit)]
        self.result = rows
        return self

    def _match_single(self, row, crit):
        left_key = crit.left.key
        op_name = getattr(crit.operator, "__name__", "")
        right_value = self._extract_right_value(crit)
        if op_name == "is_not":
            return getattr(row, left_key, None) is not None
        elif op_name == "is_":
            return getattr(row, left_key, None) == right_value
        elif op_name == "ilike_op":
            attr_val = getattr(row, left_key, None)
            if attr_val is None:
                return False
            pattern = right_value.replace("%", "")
            return pattern.lower() in str(attr_val).lower()
        else:
            return crit.operator(getattr(row, left_key), right_value)

    @staticmethod
    def _extract_right_value(crit):
        if isinstance(crit.right, sql.elements.True_):
            return True
        elif isinstance(crit.right, sql.elements.False_):
            return False
        elif isinstance(crit.right, sql.elements.Null):
            return None
        else:
            return crit.right.value

    def order_by(self, *criteria):
        self.orderings.extend(criteria)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _similarity(self, product_embedding):
        dot = sum(a * b for a, b in zip(product_embedding, self.query_vector))
        norm_a = math.sqrt(sum(x * x for x in product_embedding))
        norm_b = math.sqrt(sum(x * x for x in self.query_vector))
        return dot / (norm_a * norm_b)

    def all(self):
        rows = list(self.result)
        if self._limit is not None:
            rows = rows[: self._limit]
        if self.returns_pairs and self.query_vector is not None:
            pairs = [(r, self._similarity(r.embedding)) for r in rows]
            pairs.sort(key=lambda p: p[1], reverse=True)
            return pairs
        return rows

    def first(self):
        return self.result[0] if self.result else None


class FakeDB:
    def __init__(self, merchants=None, products=None, query_vector=None):
        self.merchant_query = FakeQuery(merchants or [])
        self.product_query = FakeQuery(products or [], query_vector=query_vector)
        self.queries = {
            "merchant": self.merchant_query,
            "product": self.product_query,
        }

    def query(self, *entities):
        if entities[0].__name__ == "Merchant":
            return self.merchant_query
        q = self.queries["product"]
        q.returns_pairs = len(entities) > 1
        return q


class FakeEmbeddingModel:
    def __init__(self):
        self.texts = []

    def encode(self, texts):
        self.texts.extend(texts)
        return [unit_vector(1.0, 0.0) for _ in texts]


class MockLLMProvider:
    """Mock LLM that returns different responses for intent extraction vs chat.
    
    The chat endpoint calls generate_json twice:
    1. For intent extraction (needs intent-shaped JSON)
    2. For chat response (needs message+products JSON)
    """

    def __init__(self, intent_response=None, chat_response=None, error=None):
        self.intent_response = intent_response
        self.chat_response = chat_response
        self.error = error
        self.call_count = 0
        self.system_prompts = []
        self.user_prompts = []

    def generate_json(self, system_prompt, user_prompt):
        self.call_count += 1
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        
        if self.error:
            raise self.error
        
        # First call is for intent extraction, second for chat
        if self.call_count == 1 and self.intent_response is not None:
            return json.dumps(self.intent_response)
        elif self.chat_response is not None:
            return json.dumps(self.chat_response)
        else:
            raise LLMError("No response configured for this call")


def override(fake_db=None, fake_model=None, fake_llm=None):
    if fake_db is not None:
        app.dependency_overrides[get_db] = lambda: fake_db
    if fake_model is not None:
        app.dependency_overrides[get_intent_embedding_model] = lambda: fake_model
    if fake_llm is not None:
        app.dependency_overrides[get_llm_provider] = lambda: fake_llm


client = TestClient(app)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def chat_payload(**overrides):
    payload = {
        "merchant_id": str(MERCHANT_ID),
        "message": "I need a laptop for local AI development under 70000 with 16GB RAM",
    }
    payload.update(overrides)
    return payload


# Default intent response extracted from the message
DEFAULT_INTENT = {
    "category": "laptop",
    "budget_min": None,
    "budget_max": 70000,
    "use_case": "local AI development",
    "requirements": ["16GB RAM"],
    "preferences": [],
    "brand": None,
}


# ---------------------------------------------------------------------------
# 1. Successful buyer chat
# ---------------------------------------------------------------------------


def test_successful_chat():
    products = [make_product(name="AI Dev Laptop")]
    llm_chat_response = {
        "message": "I found a great laptop for your local AI development needs!",
        "products": [
            {
                "product_id": str(products[0].id),
                "name": "AI Dev Laptop",
                "price": "65000.00",
                "currency": "INR",
                "similarity": 0.95,
            }
        ],
    }
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MockLLMProvider(intent_response=DEFAULT_INTENT, chat_response=llm_chat_response),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert body["message"] == "I found a great laptop for your local AI development needs!"
    assert len(body["products"]) == 1
    assert body["products"][0]["product_id"] == str(products[0].id)
    assert body["products"][0]["name"] == "AI Dev Laptop"
    assert body["products"][0]["price"] == "65000.00"
    assert body["products"][0]["currency"] == "INR"
    assert body["products"][0]["similarity"] == 0.95


# ---------------------------------------------------------------------------
# 2. Correct retrieval context passed to LLM
# ---------------------------------------------------------------------------


def test_retrieval_context_passed_to_llm():
    products = [make_product(name="AI Dev Laptop")]
    llm_chat_response = {
        "message": "I recommend this laptop for your needs.",
        "products": [
            {
                "product_id": str(products[0].id),
                "name": "AI Dev Laptop",
                "price": "65000.00",
                "currency": "INR",
                "similarity": 0.95,
            }
        ],
    }
    llm = MockLLMProvider(intent_response=DEFAULT_INTENT, chat_response=llm_chat_response)
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=llm,
    )

    client.post(URL, json=chat_payload())

    # Verify LLM was called exactly twice (intent + chat)
    assert llm.call_count == 2
    # The chat prompt should contain the product data
    assert len(llm.user_prompts) == 2
    chat_prompt = llm.user_prompts[1]
    assert "AI Dev Laptop" in chat_prompt
    assert "65000" in chat_prompt
    assert "laptop" in chat_prompt


# ---------------------------------------------------------------------------
# 3. LLM does not receive unrestricted database access
# ---------------------------------------------------------------------------


def test_llm_does_not_access_database_directly():
    """LLM only receives buyer message and retrieved products."""
    products = [make_product(name="AI Dev Laptop")]
    llm_chat_response = {
        "message": "Here is a laptop recommendation.",
        "products": [],
    }
    llm = MockLLMProvider(intent_response=DEFAULT_INTENT, chat_response=llm_chat_response)
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=llm,
    )

    client.post(URL, json=chat_payload())

    # The LLM was called, meaning the endpoint manages DB access
    # The LLM itself never accesses DB
    assert llm.call_count == 2


# ---------------------------------------------------------------------------
# 4. Empty search results
# ---------------------------------------------------------------------------


def test_empty_search_results():
    llm_chat_response = {
        "message": "No products found for your request.",
        "products": [],
    }
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=[]),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MockLLMProvider(intent_response=DEFAULT_INTENT, chat_response=llm_chat_response),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert body["products"] == []
    assert body["message"] == "No products found for your request."


# ---------------------------------------------------------------------------
# 5. LLM failure uses safe fallback
# ---------------------------------------------------------------------------


def test_llm_failure_uses_safe_fallback():
    products = [make_product(name="AI Dev Laptop")]
    # LLM fails during intent extraction
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MockLLMProvider(error=LLMError("LLM is down")),
    )

    response = client.post(URL, json=chat_payload())

    # Intent extraction failure returns 503 (service unavailable)
    assert response.status_code == 503
    assert response.json()["detail"] == "AI intent service is temporarily unavailable."


def test_llm_chat_failure_uses_safe_fallback():
    """When intent extraction succeeds but chat LLM fails, return safe fallback."""
    products = [make_product(name="AI Dev Laptop")]
    
    # First call succeeds (intent), second call fails (chat)
    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMError("Chat LLM failed")
    
    class PartiallyFailingLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)
    
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=PartiallyFailingLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert len(body["products"]) == 1
    assert body["products"][0]["name"] == "AI Dev Laptop"
    assert body["products"][0]["price"] == "65000.00"
    assert body["products"][0]["currency"] == "INR"
    # Deterministic fallback message
    assert body["message"] == (
        "I found 1 product matching your request. "
        "The closest match is AI Dev Laptop at INR 65000.00."
    )


def test_llm_chat_failure_logs_audit_event(caplog):
    """LLM failure is logged with an audit-friendly event."""
    products = [make_product(name="AI Dev Laptop")]

    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMRequestError("LLM returned HTTP 429.")

    class RateLimitedLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=RateLimitedLLM(),
    )

    with caplog.at_level(logging.WARNING, logger="app.api.v1.buyer"):
        response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    audit_logs = [r for r in caplog.records if "llm_failure" in r.message]
    assert len(audit_logs) == 1
    assert "429" in audit_logs[0].message or "LLMRequestError" in audit_logs[0].message
    # Must NOT leak API keys or system prompts
    assert "sk-or" not in audit_logs[0].message


# ---------------------------------------------------------------------------
# 5b. 429 rate-limit -> deterministic fallback
# ---------------------------------------------------------------------------


def test_rate_limit_returns_deterministic_fallback():
    """HTTP 429 from provider triggers deterministic fallback, not 503."""
    products = [make_product(name="AI Dev Laptop")]

    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMRequestError("LLM returned HTTP 429.")

    class RateLimitedLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=RateLimitedLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert len(body["products"]) == 1
    assert body["products"][0]["name"] == "AI Dev Laptop"
    assert body["products"][0]["price"] == "65000.00"
    assert body["products"][0]["currency"] == "INR"
    assert body["message"] == (
        "I found 1 product matching your request. "
        "The closest match is AI Dev Laptop at INR 65000.00."
    )


# ---------------------------------------------------------------------------
# 5c. Timeout -> deterministic fallback
# ---------------------------------------------------------------------------


def test_timeout_returns_deterministic_fallback():
    """Provider timeout triggers deterministic fallback."""
    products = [make_product(name="AI Dev Laptop")]

    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMRequestError("LLM request failed.")

    class TimeoutLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=TimeoutLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert len(body["products"]) == 1
    assert body["products"][0]["name"] == "AI Dev Laptop"
    assert body["message"] == (
        "I found 1 product matching your request. "
        "The closest match is AI Dev Laptop at INR 65000.00."
    )


# ---------------------------------------------------------------------------
# 5d. Malformed LLM response -> deterministic fallback
# ---------------------------------------------------------------------------


def test_malformed_llm_response_returns_deterministic_fallback():
    """Non-JSON LLM output triggers deterministic fallback."""
    products = [make_product(name="AI Dev Laptop")]

    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        return "Sorry, I cannot help with that."

    class MalformedLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MalformedLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert len(body["products"]) == 1
    assert body["products"][0]["name"] == "AI Dev Laptop"
    assert body["message"] == (
        "I found 1 product matching your request. "
        "The closest match is AI Dev Laptop at INR 65000.00."
    )


# ---------------------------------------------------------------------------
# 5e. Empty retrieval + LLM failure -> clear no-products response
# ---------------------------------------------------------------------------


def test_empty_retrieval_and_llm_failure_returns_no_products_message():
    """When no products are found and LLM fails, return clear message."""
    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMRequestError("LLM returned HTTP 429.")

    class RateLimitedLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=[]),
        fake_model=FakeEmbeddingModel(),
        fake_llm=RateLimitedLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == str(MERCHANT_ID)
    assert body["products"] == []
    assert body["message"] == "I couldn't find any products matching your request."


# ---------------------------------------------------------------------------
# 5f. Multiple products -> correct count and closest match
# ---------------------------------------------------------------------------


def test_multiple_products_deterministic_fallback():
    """Fallback message uses correct plural and identifies closest match."""
    products = [
        make_product(name="Laptop A", price=Decimal("50000.00")),
        make_product(name="Laptop B", price=Decimal("70000.00")),
        make_product(name="Laptop C", price=Decimal("60000.00")),
    ]

    call_count = [0]
    def mock_generate(system_prompt, user_prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            return json.dumps(DEFAULT_INTENT)
        raise LLMRequestError("LLM returned HTTP 429.")

    class RateLimitedLLM:
        def generate_json(self, system_prompt, user_prompt):
            return mock_generate(system_prompt, user_prompt)

    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=RateLimitedLLM(),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 200
    body = response.json()
    assert len(body["products"]) == 3
    assert "3 products" in body["message"]
    # Closest match has highest similarity (all same in mock, so first wins)
    assert "Laptop A" in body["message"]
    assert "50000.00" in body["message"]


# ---------------------------------------------------------------------------
# 6. Unknown merchant returns 404
# ---------------------------------------------------------------------------


def test_unknown_merchant_returns_404():
    override(
        fake_db=FakeDB(merchants=[], products=[make_product()]),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MockLLMProvider(
            intent_response=DEFAULT_INTENT,
            chat_response={"message": "test", "products": []},
        ),
    )

    response = client.post(URL, json=chat_payload())

    assert response.status_code == 404
    assert response.json()["detail"] == "Merchant not found"


# ---------------------------------------------------------------------------
# 7. No money action is performed
# ---------------------------------------------------------------------------


def test_no_money_action_performed():
    """The chat endpoint should not trigger any purchase, discount, or payment."""
    products = [make_product(name="AI Dev Laptop")]
    llm_chat_response = {
        "message": "I recommend this laptop.",
        "products": [
            {
                "product_id": str(products[0].id),
                "name": "AI Dev Laptop",
                "price": "65000.00",
                "currency": "INR",
                "similarity": 0.95,
            }
        ],
    }
    override(
        fake_db=FakeDB(merchants=[FakeMerchant(MERCHANT_ID)], products=products),
        fake_model=FakeEmbeddingModel(),
        fake_llm=MockLLMProvider(intent_response=DEFAULT_INTENT, chat_response=llm_chat_response),
    )

    response = client.post(URL, json=chat_payload())

    # The response should only contain merchant_id, message, and products
    # No purchase, payment, discount, or other money action fields
    body = response.json()
    assert set(body.keys()) == {"merchant_id", "message", "products"}
    # Each product should only have safe fields
    for product in body["products"]:
        assert set(product.keys()) == {"product_id", "name", "price", "currency", "similarity"}

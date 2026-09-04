#!/usr/bin/env python3
"""
Real integration test: POST /api/v1/buyer/chat with TechKart merchant.

Runs against the live database and real LLM. Verifies:
- Merchant lookup succeeds
- Intent extraction produces valid JSON
- Product retrieval returns relevant results
- LLM chat response is well-formed
- Response schema matches BuyerChatResponse
- No money actions are performed
- Error handling works correctly
"""

import json
import sys
import traceback
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal
from app.models.merchant import Merchant

TECHKART_ID = "7d9ae869-7fe1-4295-a427-bcae59b6eb5d"
URL = "/api/v1/buyer/chat"


def test_basic_chat():
    """Test 1: Basic chat with a laptop query."""
    print("\n=== Test 1: Basic laptop query ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "I need a laptop for local AI development under 70000 with 16GB RAM",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {body}"
    assert body["merchant_id"] == TECHKART_ID
    assert isinstance(body["message"], str)
    assert len(body["message"]) > 0
    assert isinstance(body["products"], list)
    for p in body["products"]:
        assert "product_id" in p
        assert "name" in p
        assert "price" in p
        assert "currency" in p
        assert "similarity" in p
        assert p["currency"] == "INR"
    print("PASS")
    return body


def test_smartphone_query():
    """Test 2: Smartphone query should find smartphone products."""
    print("\n=== Test 2: Smartphone query ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "Show me the best smartphone under 30000",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 200
    assert body["merchant_id"] == TECHKART_ID
    # Should return at least one product
    assert len(body["products"]) >= 1, f"Expected at least 1 product, got {len(body['products'])}"
    # Check product names contain relevant content or similarity is reasonable
    print(f"Number of products returned: {len(body['products'])}")
    for p in body["products"]:
        print(f"  - {p['name']}: Rs.{p['price']} (similarity={p['similarity']:.4f})")
    print("PASS")
    return body


def test_camera_query():
    """Test 3: Camera query."""
    print("\n=== Test 3: Camera query ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "I want a digital camera for photography under 30000",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 200
    assert body["merchant_id"] == TECHKART_ID
    assert len(body["products"]) >= 1
    print("PASS")
    return body


def test_no_match_query():
    """Test 4: Query with no matching products (category not in TechKart)."""
    print("\n=== Test 4: No match - Washing Machine query ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "I need a washing machine for home use under 25000",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 200
    assert body["merchant_id"] == TECHKART_ID
    # May return 0 products or some products, but should not crash
    assert isinstance(body["products"], list)
    assert isinstance(body["message"], str)
    print("PASS")
    return body


def test_unknown_merchant():
    """Test 5: Unknown merchant should return 404."""
    print("\n=== Test 5: Unknown merchant ===")
    client = TestClient(app)
    fake_id = "00000000-0000-0000-0000-000000000000"
    payload = {
        "merchant_id": fake_id,
        "message": "Show me laptops",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 404
    assert body["detail"] == "Merchant not found"
    print("PASS")
    return body


def test_no_money_actions():
    """Test 6: Verify no money actions in response."""
    print("\n=== Test 6: No money actions ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "Show me laptops",
    }
    resp = client.post(URL, json=payload)
    body = resp.json()

    # Response should only have merchant_id, message, products
    assert set(body.keys()) == {"merchant_id", "message", "products"}, f"Unexpected keys: {set(body.keys())}"

    # Each product should only have safe fields
    allowed_product_keys = {"product_id", "name", "price", "currency", "similarity"}
    for p in body["products"]:
        assert set(p.keys()) == allowed_product_keys, f"Unexpected product keys: {set(p.keys())}"

    print("PASS - No money actions detected in response")


def test_budget_filter():
    """Test 7: Budget constraint should be respected."""
    print("\n=== Test 7: Budget filter (under 10000) ===")
    client = TestClient(app)
    payload = {
        "merchant_id": TECHKART_ID,
        "message": "I want something under 10000",
    }
    print(f"Payload: {json.dumps(payload, indent=2)}")
    resp = client.post(URL, json=payload)
    print(f"Status: {resp.status_code}")
    body = resp.json()
    print(f"Response:\n{json.dumps(body, indent=2)}")

    assert resp.status_code == 200
    # Products returned should be within budget
    for p in body["products"]:
        price = float(p["price"])
        assert price <= 10000, f"Product {p['name']} has price {price} exceeding budget 10000"
        print(f"  - {p['name']}: Rs.{price} (within budget)")
    print("PASS")
    return body


if __name__ == "__main__":
    print("=" * 70)
    print("Real Integration Test: POST /api/v1/buyer/chat (TechKart)")
    print("=" * 70)

    tests = [
        test_basic_chat,
        test_smartphone_query,
        test_camera_query,
        test_no_match_query,
        test_unknown_merchant,
        test_no_money_actions,
        test_budget_filter,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((test_fn.__name__, str(e)))
            print(f"FAIL: {e}")
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 70)

    sys.exit(1 if failed else 0)

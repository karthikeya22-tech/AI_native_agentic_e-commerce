from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "email": "merchant@example.com",
    "name": "Test Merchant",
    "category": "electronics",
    "description": "A test merchant",
}


def test_create_merchant_success():
    user_id = str(uuid4())
    merchant_id = str(uuid4())

    with (
        patch("app.api.v1.merchants.check_merchant_exists", return_value=False) as mock_check,
        patch(
            "app.api.v1.merchants.create_merchant",
            return_value=(user_id, merchant_id),
        ) as mock_create,
    ):
        response = client.post("/api/v1/merchants", json=PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == user_id
    assert body["merchant_id"] == merchant_id
    assert body["name"] == PAYLOAD["name"]
    assert body["status"] == "active"

    mock_check.assert_called_once()
    mock_create.assert_called_once()
    request_arg = mock_create.call_args.args[1]
    assert request_arg.email == PAYLOAD["email"]
    assert request_arg.name == PAYLOAD["name"]


def test_create_merchant_duplicate_email():
    with patch("app.api.v1.merchants.check_merchant_exists", return_value=True):
        response = client.post("/api/v1/merchants", json=PAYLOAD)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

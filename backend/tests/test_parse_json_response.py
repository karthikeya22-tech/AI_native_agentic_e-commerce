import json

import pytest

from app.ai.provider import LLMRequestError, parse_json_response


def test_parses_raw_json_object():
    raw = json.dumps({"category": "laptop", "budget_max": 70000})

    assert parse_json_response(raw) == {
        "category": "laptop",
        "budget_max": 70000,
    }


def test_parses_json_fenced_with_language_tag():
    inner = {"recommendations": [{"title": "x", "priority": "high"}]}
    raw = f"```json\n{json.dumps(inner)}\n```"

    assert parse_json_response(raw) == inner


def test_parses_json_fenced_without_language_tag():
    inner = {"category": None, "budget_min": None}
    raw = f"```\n{json.dumps(inner)}\n```"

    assert parse_json_response(raw) == inner


def test_rejects_arbitrary_prose():
    with pytest.raises(LLMRequestError):
        parse_json_response("Here is your result! The category is laptop.")


def test_rejects_prose_around_fenced_json():
    raw = 'Sure! ```json\n{"a": 1}\n``` hope that helps'
    with pytest.raises(LLMRequestError):
        parse_json_response(raw)


def test_rejects_malformed_json_inside_fence():
    with pytest.raises(LLMRequestError):
        parse_json_response("```json\n{not valid}\n```")


def test_rejects_non_object_json():
    with pytest.raises(LLMRequestError):
        parse_json_response('["a", "list"]')


def test_intent_endpoint_works_with_fenced_llm_output():
    from fastapi.testclient import TestClient

    from app.ai.provider import get_llm_provider
    from app.main import app

    class FencedProvider:
        def generate_json(self, system_prompt: str, user_prompt: str) -> str:
            return (
                '```json\n{"category": "laptop", "budget_max": 70000, '
                '"budget_min": null, "use_case": "local AI development", '
                '"requirements": ["16GB RAM"], "preferences": [], '
                '"brand": null}\n```'
            )

    app.dependency_overrides[get_llm_provider] = lambda: FencedProvider()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/buyer/intent",
            json={
                "message": "I need a laptop for local AI development under 70000 with 16GB RAM"
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "laptop"
    assert body["budget_max"] == 70000.0
    assert body["requirements"] == ["16GB RAM"]

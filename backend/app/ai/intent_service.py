"""Buyer intent extraction service.

Converts a buyer's natural-language shopping request into a structured,
validated intent object. The LLM only extracts information explicitly present
in the buyer's message; it must never invent requirements. Budgets are
normalized to plain numbers after extraction so downstream retrieval gets a
deterministic shape.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.provider import (
    LLMError,
    LLMProvider,
    LLMRequestError,
    parse_json_response,
)

SYSTEM_PROMPT = """You extract structured shopping intent from a buyer's
natural-language message for an e-commerce platform.

Strict rules:
- Extract ONLY information explicitly present in the buyer's message.
- Do NOT invent categories, brands, budgets, requirements, or preferences.
- If a field is not mentioned in the message, use null (or an empty list).
- Normalize numeric budget values into plain numbers (e.g. "under ₹70,000"
  becomes 70000). Strip currency symbols and commas.
- "budget_max" is the upper spending limit; "budget_min" is the lower limit.
- "requirements" are concrete must-have specs mentioned by the buyer
  (e.g. "16GB RAM").
- "preferences" are softer likes/wants mentioned by the buyer
  (e.g. "lightweight").

Return ONLY a JSON object with this exact shape:
{
  "category": "string or null",
  "budget_min": "number or null",
  "budget_max": "number or null",
  "use_case": "string or null",
  "requirements": ["list of strings"],
  "preferences": ["list of strings"],
  "brand": "string or null"
}"""

_NUMBER_PATTERN = re.compile(r"[-+]?\d[\d,]*\.?\d*")


class IntentExtractionError(LLMError):
    """Raised when the intent cannot be produced from the LLM output."""


class BuyerIntent(BaseModel):
    category: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    use_case: str | None = None
    requirements: list[str] = []
    preferences: list[str] = []
    brand: str | None = None


def _normalize_number(value: Any) -> float | None:
    """Coerce numbers or numeric strings (with symbols/commas) to float."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _NUMBER_PATTERN.search(value.replace(",", ""))
        if not match:
            return None
        try:
            return float(Decimal(match.group()))
        except InvalidOperation:
            return None
    return None


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def build_user_prompt(message: str) -> str:
    return json.dumps({"buyer_message": message}, indent=2)


def extract_intent(message: str, provider: LLMProvider) -> BuyerIntent:
    """Extract validated structured intent from a buyer message.

    Raises:
        IntentExtractionError: if the provider fails or the response cannot
            be validated against the intent schema.
    """
    raw = provider.generate_json(SYSTEM_PROMPT, build_user_prompt(message))
    try:
        payload = parse_json_response(raw)
    except LLMRequestError as exc:
        raise IntentExtractionError(
            "LLM returned invalid JSON."
        ) from exc

    # Normalize budgets before schema validation so string values such as
    # "₹70,000" or "70,000 INR" are accepted and coerced to numbers.
    if isinstance(payload, dict):
        for key in ("budget_min", "budget_max"):
            if key in payload:
                payload[key] = _normalize_number(payload[key])

    try:
        intent = BuyerIntent(**payload)
    except ValidationError as exc:
        raise IntentExtractionError(
            "LLM returned a malformed intent object."
        ) from exc

    # Deterministic post-processing: normalize budgets and lists.
    return BuyerIntent(
        category=(intent.category.strip() or None) if isinstance(intent.category, str) else None,
        budget_min=_normalize_number(intent.budget_min),
        budget_max=_normalize_number(intent.budget_max),
        use_case=(intent.use_case.strip() or None) if isinstance(intent.use_case, str) else None,
        requirements=_normalize_string_list(intent.requirements),
        preferences=_normalize_string_list(intent.preferences),
        brand=(intent.brand.strip() or None) if isinstance(intent.brand, str) else None,
    )

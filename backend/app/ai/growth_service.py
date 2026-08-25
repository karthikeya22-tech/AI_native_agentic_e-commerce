"""AI growth recommendation service.

Converts deterministic Commerce Readiness issues into merchant-facing
recommendations. The LLM only rephrases/explains the supplied issues — it
never computes scores or invents product facts, prices, inventory, or metrics.
"""

import json
from typing import Sequence

from pydantic import BaseModel, ValidationError

from app.ai.provider import (
    LLMError,
    LLMProvider,
    parse_json_response,
)

VALID_PRIORITIES = ("low", "medium", "high")

SYSTEM_PROMPT = """You are an AI commerce advisor for an e-commerce platform.

You will receive a JSON list of catalog readiness issues that were computed
deterministically by our backend scoring engine.

Strict rules:
- Use ONLY the information contained in the supplied issues.
- Do NOT invent product facts, prices, inventory numbers, metrics, or
  statistics of any kind.
- Do NOT add recommendations for products or problems not present in the
  supplied data.
- Produce at most one recommendation per supplied issue.

Return ONLY a JSON object with this exact shape:
{
  "recommendations": [
    {
      "title": "short imperative title",
      "explanation": "why this matters for AI-driven commerce",
      "suggested_action": "concrete next step derived from the issue",
      "expected_impact": "qualitative impact description",
      "priority": "low|medium|high"
    }
  ]
}

The "priority" must be one of exactly: low, medium, high."""


class RecommendationGenerationError(LLMError):
    """Raised when recommendations cannot be produced from the LLM output."""


class Recommendation(BaseModel):
    title: str
    explanation: str
    suggested_action: str
    expected_impact: str
    priority: str

    def normalized(self) -> dict:
        priority = self.priority.strip().lower()
        if priority not in VALID_PRIORITIES:
            priority = "medium"
        return {
            "title": self.title,
            "explanation": self.explanation,
            "suggested_action": self.suggested_action,
            "expected_impact": self.expected_impact,
            "priority": priority,
        }


def build_user_prompt(issues: Sequence[dict]) -> str:
    """Render the structured issues into the user prompt."""
    compact = [
        {
            "product_name": issue.get("product_name", ""),
            "issue_type": issue.get("issue_type", ""),
            "description": issue.get("description", ""),
            "severity": issue.get("severity", ""),
            "suggested_action": issue.get("suggested_action", ""),
        }
        for issue in issues
    ]
    return json.dumps({"readiness_issues": compact}, indent=2)


def generate_recommendations(
    issues: Sequence[dict],
    provider: LLMProvider,
) -> list[dict]:
    """Generate recommendations from structured readiness issues.

    Raises:
        RecommendationGenerationError: if the provider fails or the response
            cannot be validated against the expected schema.
    """
    if not issues:
        return []

    raw = provider.generate_json(SYSTEM_PROMPT, build_user_prompt(issues))
    payload = parse_json_response(raw)

    items = payload.get("recommendations")
    if not isinstance(items, list):
        raise RecommendationGenerationError(
            "LLM response is missing the 'recommendations' list."
        )

    # Never emit more recommendations than supplied issues.
    recommendations: list[dict] = []
    for item in items[: len(issues)]:
        try:
            rec = Recommendation(**item)
        except (ValidationError, TypeError) as exc:
            raise RecommendationGenerationError(
                "LLM returned a malformed recommendation."
            ) from exc
        recommendations.append(rec.normalized())

    return recommendations

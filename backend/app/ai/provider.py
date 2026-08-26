"""LLM provider abstraction.

Keeps model/provider configuration behind a small interface so the provider
can be swapped later without touching business logic. The default
implementation speaks the OpenAI-compatible chat-completions protocol via
httpx. Credentials are read from environment variables only.
"""

import json
import re
from typing import Any, Protocol

import httpx

from app.core.config import get_settings


class LLMError(Exception):
    """Base error for LLM interactions."""


class LLMConfigurationError(LLMError):
    """Raised when the LLM is not configured (e.g. missing API key)."""


class LLMRequestError(LLMError):
    """Raised when the LLM request fails or returns an unusable response."""


class LLMProvider(Protocol):
    """Minimal contract every provider must satisfy."""

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """Return the raw JSON string produced by the model."""
        ...


class OpenAICompatibleProvider:
    """Provider for any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self.model = model if model is not None else settings.LLM_MODEL
        self.base_url = (
            base_url if base_url is not None else settings.LLM_BASE_URL
        ).rstrip("/")
        self.timeout = (
            timeout
            if timeout is not None
            else settings.LLM_TIMEOUT_SECONDS
        )

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise LLMConfigurationError(
                "LLM_API_KEY is not configured."
            )

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except LLMError:
            raise
        except httpx.HTTPStatusError as exc:
            raise LLMRequestError(
                f"LLM returned HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMRequestError("LLM request failed.") from exc


def get_llm_provider() -> LLMProvider:
    return OpenAICompatibleProvider()


_FENCED_JSON_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*\n(?P<content>.*)\n\s*```\s*$",
    re.DOTALL,
)


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object out of a raw completion string.

    Accepts raw JSON objects and JSON wrapped in Markdown code fences
    (``` or ```json). Arbitrary prose is never accepted; if the content
    is still not valid JSON, LLMRequestError is raised.
    """
    if not isinstance(raw, str):
        raise LLMRequestError("LLM response was not text.")

    candidate = raw.strip()

    match = _FENCED_JSON_PATTERN.match(candidate)
    if match:
        candidate = match.group("content").strip()

    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMRequestError("LLM returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise LLMRequestError("LLM response was not a JSON object.")
    return value

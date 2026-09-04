from app.ai.provider import OpenAICompatibleProvider, LLMError

try:
    raw = OpenAICompatibleProvider().generate_json(
        "Return JSON only.", '{"test": true}'
    )
    print("OK:", raw[:300])
except LLMError as exc:
    import traceback

    traceback.print_exc()

import json
import sys

sys.path.insert(0, r"C:\Users\srika\AI_native_agentic_e-commerce\backend")

from app.ai.intent_service import SYSTEM_PROMPT, extract_intent
from app.ai.provider import OpenAICompatibleProvider, LLMError

message = (
    "I need a laptop for local AI development under 70000 with 16GB RAM"
)

try:
    intent = extract_intent(message, OpenAICompatibleProvider())
    print("INTENT:", intent.model_dump())
except LLMError:
    import traceback

    traceback.print_exc()

# Also show the raw model output for inspection
provider = OpenAICompatibleProvider()
try:
    raw = provider.generate_json(
        SYSTEM_PROMPT,
        json.dumps({"buyer_message": message}, indent=2),
    )
    print("RAW:", raw[:500])
except LLMError:
    import traceback

    traceback.print_exc()

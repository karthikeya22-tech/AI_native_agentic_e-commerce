from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.intent_service import IntentExtractionError, extract_intent
from app.ai.provider import LLMError, get_llm_provider, LLMProvider
from app.api.v1.schemas import BuyerIntentRequest, BuyerIntentResponse

router = APIRouter(prefix="/api/v1/buyer", tags=["buyer"])


@router.post("/intent", response_model=BuyerIntentResponse)
def extract_buyer_intent(
    request: BuyerIntentRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> BuyerIntentResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message must not be empty.",
        )

    try:
        intent = extract_intent(message, llm_provider)
    except IntentExtractionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an unusable response.",
        )
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI intent service is temporarily unavailable.",
        )

    return BuyerIntentResponse(**intent.model_dump())

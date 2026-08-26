import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.intent_service import (
    IntentExtractionError,
    extract_intent,
    deterministic_extract_intent,
)
from app.ai.provider import LLMError, get_llm_provider, LLMProvider, parse_json_response
from app.api.v1.schemas import (
    BuyerChatRequest,
    BuyerChatProduct,
    BuyerChatResponse,
    BuyerIntentRequest,
    BuyerIntentResponse,
    BuyerSearchRequest,
    BuyerSearchResponse,
    BuyerSearchResultItem,
)
from app.db.session import get_db
from app.models.merchant import Merchant
from app.services.retrieval.product_search import (
    DEFAULT_LIMIT,
    get_intent_embedding_model,
    search_products_for_intent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/buyer", tags=["buyer"])


def _build_deterministic_fallback_message(
    products_for_llm: list[dict],
    intent,
) -> str:
    """Build a concise, deterministic fallback message from retrieved products.

    Never invents specifications, prices, inventory, reviews, discounts,
    or performance claims.  Uses only data already present in the retrieved
    product list.
    """
    if not products_for_llm:
        return "I couldn't find any products matching your request."

    n = len(products_for_llm)
    closest = min(products_for_llm, key=lambda p: p["similarity"])
    count_word = "product" if n == 1 else "products"
    return (
        f"I found {n} {count_word} matching your request. "
        f"The closest match is {closest['name']} at {closest['currency']} "
        f"{closest['price']}."
    )


def _log_llm_failure(
    *,
    failure_type: str,
    merchant_id: str,
    buyer_message: str,
    phase: str,
    detail: str = "",
) -> None:
    """Log an audit-friendly event when the LLM call fails.

    Intentionally does NOT log API keys, raw provider responses, or
    internal system prompts.  Only non-sensitive metadata is recorded.
    """
    event = {
        "event": "llm_failure",
        "timestamp": time.time(),
        "phase": phase,
        "failure_type": failure_type,
        "merchant_id": merchant_id,
        "buyer_message_preview": buyer_message[:120],
        "detail": detail,
    }
    logger.warning("buyer_chat llm_failure: %s", event)


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


@router.post("/search", response_model=BuyerSearchResponse)
def search_products(
    request: BuyerSearchRequest,
    db: Session = Depends(get_db),
    embedding_model=Depends(get_intent_embedding_model),
) -> BuyerSearchResponse:
    merchant = db.query(Merchant).filter(Merchant.id == request.merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    matches = search_products_for_intent(
        db,
        request,
        model=embedding_model,
        limit=DEFAULT_LIMIT,
    )

    results = [
        BuyerSearchResultItem(
            product_id=UUID(str(match.product.id)),
            name=match.product.name,
            description=match.product.description,
            category=match.product.category,
            price=str(match.product.price),
            currency=match.product.currency,
            inventory_quantity=match.product.inventory_quantity,
            similarity=round(match.similarity, 4),
        )
        for match in matches
    ]
    return BuyerSearchResponse(results=results)


@router.post("/chat", response_model=BuyerChatResponse)
def buyer_chat(
    request: BuyerChatRequest,
    db: Session = Depends(get_db),
    embedding_model=Depends(get_intent_embedding_model),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> BuyerChatResponse:
    # 1. Verify merchant exists
    merchant = db.query(Merchant).filter(Merchant.id == request.merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    # 2. Extract structured intent from buyer's message
    try:
        intent = extract_intent(request.message, llm_provider)
    except IntentExtractionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an unusable response.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI intent service is temporarily unavailable.",
        )

    # 3. Combine intent with merchant_id for retrieval
    search_request = BuyerSearchRequest(
        merchant_id=request.merchant_id,
        category=intent.category,
        budget_min=intent.budget_min,
        budget_max=intent.budget_max,
        use_case=intent.use_case,
        requirements=intent.requirements,
        preferences=intent.preferences,
        brand=intent.brand,
    )

    # 4. Retrieve relevant products using deterministic constraints
    try:
        matches = search_products_for_intent(
            db,
            search_request,
            model=embedding_model,
            limit=DEFAULT_LIMIT,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product retrieval failed.",
        )

    # 5. Prepare product data for LLM
    products_for_llm = [
        {
            "product_id": str(p.product.id),
            "name": p.product.name,
            "description": p.product.description,
            "category": p.product.category,
            "price": str(p.product.price),
            "currency": p.product.currency,
            "inventory_quantity": p.product.inventory_quantity,
            "similarity": round(p.similarity, 4),
        }
        for p in matches
    ]

    # 5. Build prompts for LLM
    system_prompt = """You are a helpful shopping assistant for an e-commerce platform.
- Explain why retrieved products match the buyer's request.
- Compare candidates when useful.
- Clearly state uncertainty when evidence is insufficient.
- Use ONLY the supplied buyer intent and retrieved product data.
- Never invent product specifications, prices, inventory, discounts, reviews, or performance claims.
- Never claim an action was completed unless the backend actually completed it.
- Structure your response to include a brief message to the buyer and product suggestions."""

    # Format product summary for LLM
    products_text = "\n".join(
        f"- {p['name']}: {p['description']} (₹{p['price']}, similarity {p['similarity']})"
        for p in products_for_llm
    )

    user_prompt = f"""Buyer message: {request.message}

Extracted intent:
- Category: {intent.category}
- Budget max: {intent.budget_max}
- Budget min: {intent.budget_min}
- Use case: {intent.use_case}
- Requirements: {', '.join(intent.requirements) if intent.requirements else 'none'}
- Preferences: {', '.join(intent.preferences) if intent.preferences else 'none'}
- Brand: {intent.brand}

Available products:
{products_text or '(no products found)'}

Please provide a helpful shopping response to the buyer. Include:
1. A brief message addressing the buyer's request.
2. Product recommendations from the available list, explaining why each matches.
3. If no products are suitable, clearly state that no suitable products were found.
4. Never invent specifications or claim actions were completed."""

    # 6. Call LLM
    try:
        raw = llm_provider.generate_json(system_prompt, user_prompt)
    except Exception as exc:
        _log_llm_failure(
            failure_type=type(exc).__name__,
            merchant_id=str(merchant.id),
            buyer_message=request.message,
            phase="chat_generation",
            detail=str(exc)[:200],
        )
        fallback_products = [
            BuyerChatProduct(
                product_id=p["product_id"],
                name=p["name"],
                price=p["price"],
                currency=p["currency"],
                similarity=p["similarity"],
            )
            for p in products_for_llm
        ]
        fallback_message = _build_deterministic_fallback_message(
            products_for_llm, intent
        )
        return BuyerChatResponse(
            merchant_id=str(merchant.id),
            message=fallback_message,
            products=fallback_products,
        )

    # 7. Parse and return structured response
    # The LLM should output JSON with "message" and "products" fields.
    # Accept both raw JSON and JSON-wrapped-in-markdown-fences (parse_json_response handles it).
    try:
        parsed = parse_json_response(raw)
    except Exception as exc:
        _log_llm_failure(
            failure_type="malformed_response",
            merchant_id=str(merchant.id),
            buyer_message=request.message,
            phase="response_parsing",
            detail=str(exc)[:200],
        )
        fallback_products = [
            BuyerChatProduct(
                product_id=p["product_id"],
                name=p["name"],
                price=p["price"],
                currency=p["currency"],
                similarity=p["similarity"],
            )
            for p in products_for_llm
        ]
        fallback_message = _build_deterministic_fallback_message(
            products_for_llm, intent
        )
        return BuyerChatResponse(
            merchant_id=str(merchant.id),
            message=fallback_message,
            products=fallback_products,
        )

    # Extract products from LLM response
    llm_products = parsed.get("products", [])
    product_items = []
    for lp in llm_products:
        # Map LLM product fields to our schema; safely handle missing fields.
        pid = lp.get("product_id") or lp.get("id")
        pname = lp.get("name") or lp.get("product_name")
        price = lp.get("price") or lp.get("product_price") or "0.00"
        currency = lp.get("currency") or "INR"
        sim = lp.get("similarity") or lp.get("similarity_score") or 0.0
        product_items.append(
            BuyerChatProduct(
                product_id=UUID(str(pid)) if pid else None,
                name=str(pname) if pname else "Unnamed product",
                price=str(price),
                currency=str(currency),
                similarity=float(sim) if sim is not None else 0.0,
            )
        )

    # Use LLM's message or fallback
    final_message = parsed.get("message", "Here are some product recommendations for you.")

    return BuyerChatResponse(
        merchant_id=str(merchant.id),
        message=final_message,
        products=product_items,
    )

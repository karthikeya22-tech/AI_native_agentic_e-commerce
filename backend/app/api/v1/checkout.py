"""Buyer checkout and payment endpoints.

SAFETY RULES:
- Buyer must explicitly initiate checkout.
- Server re-reads product price from DB. Never trust frontend-supplied price.
- Payment verification is server-side only.
- AI agent has NO authority over payment.
- TEST MODE ONLY. No real money is ever charged.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.api.v1.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    WebhookResponse,
)
from app.api.v1.order_service import (
    CheckoutError,
    IdempotentPaymentError,
    InvalidQuantityError,
    MerchantNotFoundError,
    OrderNotFoundError,
    OrderNotInStateError,
    OutOfStockError,
    ProductNotFoundError,
    create_order,
    handle_webhook,
    verify_payment,
)
from app.api.v1.razorpay_service import (
    RazorpayConfigError,
    RazorpayVerificationError,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/buyer", tags=["buyer-checkout"])


# ---------------------------------------------------------------------------
# Create checkout order
# ---------------------------------------------------------------------------

@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def checkout(
    request: CheckoutRequest,
    db: Session = Depends(get_db),
) -> CheckoutResponse:
    """Create a pending order and Razorpay TEST MODE payment order.

    This endpoint:
    1. Validates merchant, product, and inventory server-side
    2. Re-reads product price from database (never trusts frontend)
    3. Creates a pending order in our database
    4. Creates a Razorpay test mode order
    5. Returns order details + Razorpay order info for frontend payment

    The frontend uses the returned Razorpay order info to open the
    Razorpay checkout widget. No real money is charged in test mode.
    """
    try:
        result = create_order(
            db,
            merchant_id=str(request.merchant_id),
            product_id=str(request.product_id),
            quantity=request.quantity,
        )
        return CheckoutResponse(**result)

    except MerchantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ProductNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OutOfStockError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except InvalidQuantityError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except CheckoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checkout failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Verify payment
# ---------------------------------------------------------------------------

@router.post(
    "/verify-payment",
    response_model=PaymentVerifyResponse,
)
def verify_payment_endpoint(
    request: PaymentVerifyRequest,
    db: Session = Depends(get_db),
) -> PaymentVerifyResponse:
    """Verify Razorpay payment signature and mark order as paid.

    This endpoint:
    1. Finds the order in our database
    2. Verifies the Razorpay signature server-side
    3. Marks the order as paid
    4. Decrements inventory (exactly once, idempotent)
    5. Records audit events

    IDEMPOTENT: If the order is already paid, returns existing state
    without double-charging or decrementing inventory again.
    """
    try:
        result = verify_payment(
            db,
            order_id=str(request.order_id),
            razorpay_order_id=request.razorpay_order_id,
            razorpay_payment_id=request.razorpay_payment_id,
            razorpay_signature=request.razorpay_signature,
        )
        return PaymentVerifyResponse(**result)

    except OrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OrderNotInStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except RazorpayVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Payment verification failed: {exc}",
        )
    except IdempotentPaymentError as exc:
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail=str(exc),
        )
    except CheckoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment verification failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Razorpay webhook
# ---------------------------------------------------------------------------

@router.post(
    "/webhook/razorpay",
    response_model=WebhookResponse,
)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> WebhookResponse:
    """Handle Razorpay webhook notifications.

    Verifies webhook signature, then processes payment events.
    Idempotent: duplicate events are safely ignored.
    """
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook signature
    webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None)
    if webhook_secret:
        try:
            verify_webhook_signature(
                body,
                signature,
                webhook_secret=webhook_secret,
            )
        except RazorpayVerificationError as exc:
            logger.warning("webhook_signature_invalid: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # Parse payload
    try:
        import json
        payload = json.loads(body)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    event_type = payload.get("event", "")
    logger.info("webhook_received: event=%s", event_type)

    result = handle_webhook(db, event_type=event_type, payload=payload)
    return WebhookResponse(**result)

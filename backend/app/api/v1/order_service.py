"""Order and checkout service.

Manages the complete order lifecycle:
    pending → payment_created → paid
    pending → payment_failed → cancelled

SAFETY RULES:
- Server re-reads product price from DB. Never trust frontend-supplied price.
- Inventory is decremented ONLY after verified payment, exactly once.
- Repeated payment verification is idempotent.
- No LLM calls. All operations are deterministic.
- Buyer must explicitly initiate checkout.
- AI agent has NO authority over payment.
"""

import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.merchant import Merchant, MerchantStatus
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.api.v1.audit_service import record_audit_event
from app.api.v1.razorpay_service import (
    RazorpayError,
    RazorpayOrderError,
    RazorpayVerificationError,
    create_razorpay_order,
    verify_razorpay_signature,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class CheckoutError(Exception):
    """Base error for checkout operations."""
    pass


class MerchantNotFoundError(CheckoutError):
    """Merchant does not exist or is inactive."""
    pass


class ProductNotFoundError(CheckoutError):
    """Product does not exist, is inactive, or belongs to wrong merchant."""
    pass


class OutOfStockError(CheckoutError):
    """Product has insufficient inventory."""
    pass


class InvalidQuantityError(CheckoutError):
    """Quantity is invalid (must be positive integer)."""
    pass


class OrderNotFoundError(CheckoutError):
    """Order does not exist."""
    pass


class OrderNotInStateError(CheckoutError):
    """Order is not in the required state for this operation."""
    pass


class IdempotentPaymentError(CheckoutError):
    """Payment has already been processed for this order."""
    pass


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------

def create_order(
    db: Session,
    *,
    merchant_id: str,
    product_id: str,
    quantity: int,
) -> dict[str, Any]:
    """Create a pending order and Razorpay test mode payment order.

    This function:
    1. Validates merchant exists and is active
    2. Validates product exists, is active, belongs to merchant, has inventory
    3. Re-reads product price from DB (never trusts frontend)
    4. Calculates total server-side
    5. Creates a pending Order record
    6. Creates a Razorpay test mode order
    7. Updates order with Razorpay order ID
    8. Records audit events

    Args:
        db: Database session.
        merchant_id: UUID string of the merchant.
        product_id: UUID string of the product.
        quantity: Number of units (must be >= 1).

    Returns:
        dict with order details and Razorpay order info.

    Raises:
        MerchantNotFoundError: Merchant not found or inactive.
        ProductNotFoundError: Product not found, inactive, or wrong merchant.
        OutOfStockError: Insufficient inventory.
        InvalidQuantityError: Quantity < 1.
        CheckoutError: Other checkout errors.
    """
    # --- Validate quantity ---
    if not isinstance(quantity, int) or quantity < 1:
        raise InvalidQuantityError(
            f"Quantity must be a positive integer, got {quantity}"
        )

    # --- Validate merchant ---
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None or merchant.status != MerchantStatus.ACTIVE:
        raise MerchantNotFoundError(
            f"Merchant {merchant_id} not found or inactive"
        )

    # --- Validate product ---
    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.merchant_id == merchant_id,
            Product.is_active == True,
        )
        .first()
    )
    if product is None:
        raise ProductNotFoundError(
            f"Product {product_id} not found, inactive, "
            f"or does not belong to merchant {merchant_id}"
        )

    # --- Validate inventory ---
    if product.inventory_quantity < quantity:
        raise OutOfStockError(
            f"Insufficient inventory: requested {quantity}, "
            f"available {product.inventory_quantity}"
        )

    # --- Server-side price calculation ---
    unit_price = Decimal(str(product.price))
    total_amount = (unit_price * quantity).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # --- Audit: checkout_started ---
    order_idempotency_key = uuid.uuid4().hex[:16]
    record_audit_event(
        event_type="checkout_started",
        merchant_id=str(merchant_id),
        opportunity_id=order_idempotency_key,
        actor="buyer",
        status="initiated",
        reason="Buyer initiated checkout",
        metadata={
            "product_id": str(product_id),
            "product_name": product.name,
            "quantity": quantity,
            "unit_price": str(unit_price),
            "total_amount": str(total_amount),
            "currency": product.currency,
        },
    )

    # --- Create pending order ---
    order = Order(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        currency=product.currency,
        status=OrderStatus.PENDING,
        order_metadata={
            "product_name": product.name,
            "merchant_name": merchant.name,
        },
    )
    db.add(order)
    db.flush()

    # --- Audit: order_created ---
    record_audit_event(
        event_type="order_created",
        merchant_id=str(merchant_id),
        opportunity_id=str(order.id),
        actor="system",
        status="pending",
        reason="Pending order created",
        metadata={
            "order_id": str(order.id),
            "product_id": str(product_id),
            "quantity": quantity,
            "total_amount": str(total_amount),
            "currency": product.currency,
        },
    )

    # --- Create Razorpay test mode order ---
    try:
        razorpay_amount_paise = int(total_amount * 100)
        razorpay_order = create_razorpay_order(
            amount_paise=razorpay_amount_paise,
            currency=product.currency,
            receipt=f"order_{order.id}",
            notes={
                "order_id": str(order.id),
                "merchant_id": str(merchant_id),
                "product_name": product.name[:50],
                "environment": "TEST_MODE",
            },
        )

        order.razorpay_order_id = razorpay_order.get("id")
        order.status = OrderStatus.PAYMENT_CREATED

        # --- Audit: payment_order_created ---
        record_audit_event(
            event_type="payment_order_created",
            merchant_id=str(merchant_id),
            opportunity_id=str(order.id),
            actor="system",
            status="payment_created",
            reason="Razorpay test mode order created",
            metadata={
                "order_id": str(order.id),
                "razorpay_order_id": order.razorpay_order_id,
                "amount_paise": razorpay_amount_paise,
                "currency": product.currency,
                "environment": "TEST_MODE",
            },
        )

        db.commit()

        return {
            "order_id": str(order.id),
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_key_id": _get_razorpay_key_id(),
            "amount_paise": razorpay_amount_paise,
            "currency": product.currency,
            "product_name": product.name,
            "unit_price": str(unit_price),
            "total_amount": str(total_amount),
            "quantity": quantity,
            "merchant_name": merchant.name,
            "status": order.status.value,
            "environment": "TEST_MODE",
        }

    except RazorpayOrderError as exc:
        order.status = OrderStatus.PAYMENT_FAILED
        db.commit()

        record_audit_event(
            event_type="payment_failed",
            merchant_id=str(merchant_id),
            opportunity_id=str(order.id),
            actor="system",
            status="payment_failed",
            reason=f"Razorpay order creation failed: {exc}",
            metadata={
                "order_id": str(order.id),
                "error_type": "razorpay_order_creation_failed",
            },
        )

        raise CheckoutError(
            f"Failed to create payment order: {exc}"
        ) from exc


def _get_razorpay_key_id() -> str:
    """Get Razorpay key ID for frontend (safe to expose, not secret)."""
    from app.core.config import get_settings
    settings = get_settings()
    return getattr(settings, "RAZORPAY_KEY_ID", "")


# ---------------------------------------------------------------------------
# Payment verification
# ---------------------------------------------------------------------------

def verify_payment(
    db: Session,
    *,
    order_id: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> dict[str, Any]:
    """Verify payment signature and mark order as paid.

    IDEMPOTENT: If the order is already paid, returns the existing state
    without double-charging or decrementing inventory again.

    Args:
        db: Database session.
        order_id: Our internal order UUID string.
        razorpay_order_id: Razorpay order ID.
        razorpay_payment_id: Razorpay payment ID.
        razorpay_signature: Razorpay signature to verify.

    Returns:
        dict with order status after verification.

    Raises:
        OrderNotFoundError: Order not found.
        OrderNotInStateError: Order is not in payment_created state.
        RazorpayVerificationError: Signature verification failed.
        CheckoutError: Other errors.
    """
    # --- Find order ---
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} not found")

    # --- Audit: payment_verification_requested ---
    record_audit_event(
        event_type="payment_verification_requested",
        merchant_id=str(order.merchant_id),
        opportunity_id=order_id,
        actor="buyer",
        status="verifying",
        reason="Payment verification requested",
        metadata={
            "order_id": order_id,
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
        },
    )

    # --- Idempotency: already paid ---
    if order.status == OrderStatus.PAID:
        logger.info(
            "verify_payment_idempotent: order=%s already paid", order_id
        )
        record_audit_event(
            event_type="payment_verified",
            merchant_id=str(order.merchant_id),
            opportunity_id=order_id,
            actor="system",
            status="idempotent",
            reason="Order already paid; skipping duplicate verification",
            metadata={
                "order_id": order_id,
                "razorpay_payment_id": order.razorpay_payment_id,
                "idempotent": True,
            },
        )
        return {
            "order_id": order_id,
            "status": order.status.value,
            "razorpay_payment_id": order.razorpay_payment_id,
            "idempotent": True,
        }

    # --- State check ---
    if order.status != OrderStatus.PAYMENT_CREATED:
        raise OrderNotInStateError(
            f"Order {order_id} is in state '{order.status.value}', "
            f"expected 'payment_created'"
        )

    # --- Verify signature ---
    try:
        verify_razorpay_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )
    except RazorpayVerificationError as exc:
        order.status = OrderStatus.PAYMENT_FAILED
        db.commit()

        record_audit_event(
            event_type="payment_failed",
            merchant_id=str(order.merchant_id),
            opportunity_id=order_id,
            actor="system",
            status="payment_failed",
            reason=f"Signature verification failed: {exc}",
            metadata={
                "order_id": order_id,
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "error_type": "signature_verification_failed",
            },
        )

        raise

    # --- Mark as paid ---
    order.razorpay_payment_id = razorpay_payment_id
    order.razorpay_signature = razorpay_signature
    order.status = OrderStatus.PAID

    # --- Audit: payment_verified ---
    record_audit_event(
        event_type="payment_verified",
        merchant_id=str(order.merchant_id),
        opportunity_id=order_id,
        actor="system",
        status="verified",
        reason="Payment signature verified successfully",
        metadata={
            "order_id": order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "total_amount": str(order.total_amount),
        },
    )

    # --- Decrement inventory (exactly once) ---
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if product is not None:
        old_inventory = product.inventory_quantity
        product.inventory_quantity = max(0, product.inventory_quantity - order.quantity)

        # --- Audit: inventory_updated ---
        record_audit_event(
            event_type="inventory_updated",
            merchant_id=str(order.merchant_id),
            opportunity_id=order_id,
            actor="system",
            status="updated",
            reason=f"Inventory decremented by {order.quantity}",
            metadata={
                "product_id": str(order.product_id),
                "old_inventory": old_inventory,
                "new_inventory": product.inventory_quantity,
                "decremented_by": order.quantity,
            },
        )

    # --- Audit: order_paid ---
    record_audit_event(
        event_type="order_paid",
        merchant_id=str(order.merchant_id),
        opportunity_id=order_id,
        actor="system",
        status="paid",
        reason="Order marked as paid after successful verification",
        metadata={
            "order_id": order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "total_amount": str(order.total_amount),
            "currency": order.currency,
        },
    )

    db.commit()

    return {
        "order_id": order_id,
        "status": order.status.value,
        "razorpay_payment_id": razorpay_payment_id,
        "total_amount": str(order.total_amount),
        "idempotent": False,
    }


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

def handle_webhook(
    db: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Handle Razorpay webhook events.

    Processes payment.captured and payment.failed events.
    Idempotent: duplicate events are safely ignored.

    Args:
        db: Database session.
        event_type: The Razorpay event type string.
        payload: The full webhook payload.

    Returns:
        dict with processing result.
    """
    payment = payload.get("payload", {}).get("payment", {})
    entity = payment.get("entity", {})

    razorpay_order_id = entity.get("order_id")
    razorpay_payment_id = entity.get("id")
    payment_status = entity.get("status")

    if not razorpay_order_id:
        logger.warning("webhook_missing_order_id: event=%s", event_type)
        return {"status": "ignored", "reason": "missing order_id"}

    # Find order by razorpay_order_id
    order = (
        db.query(Order)
        .filter(Order.razorpay_order_id == razorpay_order_id)
        .first()
    )
    if order is None:
        logger.warning(
            "webhook_order_not_found: razorpay_order_id=%s",
            razorpay_order_id,
        )
        return {"status": "ignored", "reason": "order not found"}

    # Idempotency: already paid
    if order.status == OrderStatus.PAID:
        logger.info(
            "webhook_idempotent: order=%s already paid", order.id
        )
        return {"status": "idempotent", "order_id": str(order.id)}

    if event_type == "payment.captured" and payment_status == "captured":
        order.razorpay_payment_id = razorpay_payment_id
        order.status = OrderStatus.PAID

        # Decrement inventory
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if product is not None:
            old_inventory = product.inventory_quantity
            product.inventory_quantity = max(
                0, product.inventory_quantity - order.quantity
            )
            record_audit_event(
                event_type="inventory_updated",
                merchant_id=str(order.merchant_id),
                opportunity_id=str(order.id),
                actor="system",
                status="updated",
                reason="Inventory decremented via webhook",
                metadata={
                    "product_id": str(order.product_id),
                    "old_inventory": old_inventory,
                    "new_inventory": product.inventory_quantity,
                    "decremented_by": order.quantity,
                },
            )

        record_audit_event(
            event_type="order_paid",
            merchant_id=str(order.merchant_id),
            opportunity_id=str(order.id),
            actor="system",
            status="paid",
            reason="Order paid via webhook confirmation",
            metadata={
                "order_id": str(order.id),
                "razorpay_payment_id": razorpay_payment_id,
                "webhook_event": event_type,
            },
        )

        db.commit()
        return {"status": "paid", "order_id": str(order.id)}

    elif event_type == "payment.failed":
        order.status = OrderStatus.PAYMENT_FAILED
        record_audit_event(
            event_type="payment_failed",
            merchant_id=str(order.merchant_id),
            opportunity_id=str(order.id),
            actor="system",
            status="payment_failed",
            reason=f"Payment failed via webhook: {event_type}",
            metadata={
                "order_id": str(order.id),
                "razorpay_payment_id": razorpay_payment_id,
                "webhook_event": event_type,
            },
        )
        db.commit()
        return {"status": "payment_failed", "order_id": str(order.id)}

    logger.info(
        "webhook_ignored: event=%s order=%s", event_type, order.id
    )
    return {"status": "ignored", "reason": f"unhandled event: {event_type}"}

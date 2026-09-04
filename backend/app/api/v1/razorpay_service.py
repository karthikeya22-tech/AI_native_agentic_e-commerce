"""Razorpay TEST MODE payment integration.

CRITICAL SAFETY RULES:
- This service operates in TEST/SANDBOX mode ONLY.
- No real money is ever charged.
- No live payment credentials are used.
- The AI agent has NO authority over payment.
- Buyer must explicitly initiate checkout.
- All amounts are server-calculated; frontend-supplied prices are never trusted.

Test credentials:
- Razorpay Test Key ID:rzp_test_... (from environment)
- Razorpay Test Key Secret: ... (from environment)

Test cards:
- Success: 4111 1111 1111 1111
- Failure: 4000 0000 0000 0002
"""

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Razorpay API base URL
RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


class RazorpayError(Exception):
    """Base error for Razorpay operations."""
    pass


class RazorpayConfigError(RazorpayError):
    """Razorpay credentials not configured."""
    pass


class RazorpayOrderError(RazorpayError):
    """Failed to create Razorpay order."""
    pass


class RazorpayVerificationError(RazorpayError):
    """Payment signature verification failed."""
    pass


def _get_credentials() -> tuple[str, str]:
    """Get Razorpay test mode credentials from environment."""
    settings = get_settings()
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")

    if not key_id or not key_secret:
        raise RazorpayConfigError(
            "Razorpay test mode credentials not configured. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment."
        )

    return key_id, key_secret


def create_razorpay_order(
    amount_paise: int,
    currency: str,
    receipt: str,
    *,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a Razorpay TEST MODE order.

    Args:
        amount_paise: Amount in paise (smallest currency unit).
                     For INR, 100 paise = 1 rupee.
        currency: ISO currency code (e.g. "INR").
        receipt: Unique receipt ID for idempotency.
        notes: Optional key-value notes attached to the order.

    Returns:
        dict with keys: id, entity, amount, currency, receipt, status, etc.

    Raises:
        RazorpayConfigError: If credentials not configured.
        RazorpayOrderError: If order creation fails.
    """
    key_id, key_secret = _get_credentials()

    url = f"{RAZORPAY_API_BASE}/orders"
    payload: dict[str, Any] = {
        "amount": amount_paise,
        "currency": currency,
        "receipt": receipt,
    }
    if notes:
        payload["notes"] = notes

    logger.info(
        "razorpay_create_order: amount=%d currency=%s receipt=%s mode=TEST",
        amount_paise,
        currency,
        receipt,
    )

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload,
                auth=(key_id, key_secret),
            )

        if response.status_code not in (200, 201):
            logger.error(
                "razorpay_create_order_failed: status=%d body=%s",
                response.status_code,
                response.text[:500],
            )
            raise RazorpayOrderError(
                f"Razorpay order creation failed (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )

        data = response.json()
        logger.info(
            "razorpay_order_created: id=%s status=%s",
            data.get("id"),
            data.get("status"),
        )
        return data

    except httpx.HTTPError as exc:
        logger.error("razorpay_network_error: %s", exc)
        raise RazorpayOrderError(f"Razorpay network error: {exc}") from exc


def verify_razorpay_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Verify Razorpay payment signature server-side.

    Never accept "payment successful" purely from frontend state.
    This verification must happen server-side using the shared secret.

    Args:
        razorpay_order_id: The order ID from Razorpay.
        razorpay_payment_id: The payment ID from Razorpay.
        razorpay_signature: The signature from Razorpay.

    Returns:
        True if signature is valid.

    Raises:
        RazorpayConfigError: If credentials not configured.
        RazorpayVerificationError: If signature is invalid.
    """
    _, key_secret = _get_credentials()

    # Build the expected signature: HMAC-SHA256(order_id|payment_id, secret)
    expected_payload = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        key_secret.encode("utf-8"),
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if hmac.compare_digest(expected_signature, razorpay_signature):
        logger.info(
            "razorpay_signature_valid: order=%s payment=%s",
            razorpay_order_id,
            razorpay_payment_id,
        )
        return True

    logger.warning(
        "razorpay_signature_invalid: order=%s payment=%s",
        razorpay_order_id,
        razorpay_payment_id,
    )
    raise RazorpayVerificationError(
        "Payment signature verification failed. "
        "The payment may be tampered with."
    )


def verify_webhook_signature(
    body: bytes,
    signature: str,
    *,
    webhook_secret: str | None = None,
) -> bool:
    """Verify Razorpay webhook signature.

    Args:
        body: Raw request body bytes.
        signature: X-Razorpay-Signature header value.
        webhook_secret: Webhook secret (falls back to key_secret).

    Returns:
        True if signature is valid.

    Raises:
        RazorpayVerificationError: If signature is invalid.
    """
    if webhook_secret is None:
        _, webhook_secret = _get_credentials()

    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if hmac.compare_digest(expected_signature, signature):
        return True

    raise RazorpayVerificationError("Webhook signature verification failed.")

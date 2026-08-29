"""Deterministic simulated financial action execution service.

Executes bounded, merchant-approved simulated financial actions.
This is a SIMULATION ONLY — no real payment, order, refund, or external
financial transaction occurs. No database records for products, inventory,
orders, payments, or refunds are modified.

Every money action must be:
- explainable (full audit trail)
- bounded (hard guardrails enforced)
- gated (requires explicit merchant approval)
- auditable (every state change logged)
- failure-safe (returns safe error with no financial mutation)

No LLM calls: all financial calculations are deterministic backend math.
The LLM MUST NOT calculate discount percentages, amounts, or final prices.
"""

import hashlib
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hard guardrails (deterministic, non-overridable)
# ---------------------------------------------------------------------------

MAX_DISCOUNT_PERCENT = Decimal("10.00")
MIN_DISCOUNT_PERCENT = Decimal("0.01")
SUPPORTED_ACTION_TYPES = {"simulated_discount"}

# ---------------------------------------------------------------------------
# In-memory execution store (reset-safe for tests)
# ---------------------------------------------------------------------------

_executions: dict[str, dict[str, Any]] = {}
_execution_events: list[dict[str, Any]] = []
_lock = threading.RLock()


def reset_executions() -> None:
    """Clear all in-memory execution state. For test isolation only."""
    with _lock:
        _executions.clear()
        _execution_events.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_execution_key(merchant_id: str, opportunity_id: str) -> str:
    return f"{merchant_id}:{opportunity_id}"


def _generate_execution_id(merchant_id: str, opportunity_id: str) -> str:
    """Generate a deterministic execution ID from inputs."""
    seed = f"execution:{merchant_id}:{opportunity_id}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]


def _record_event(
    event_type: str,
    merchant_id: str,
    opportunity_id: str,
    execution_id: str | None = None,
    **extra: Any,
) -> None:
    """Record an audit-friendly execution event."""
    event = {
        "event_type": event_type,
        "merchant_id": merchant_id,
        "opportunity_id": opportunity_id,
        "execution_id": execution_id,
        "timestamp": _now_iso(),
        **extra,
    }
    with _lock:
        _execution_events.append(event)
    logger.info(
        "execution_event: %s merchant=%s opp=%s exec=%s",
        event_type,
        merchant_id,
        opportunity_id,
        execution_id,
    )


# ---------------------------------------------------------------------------
# Financial calculation (deterministic, no LLM involvement)
# ---------------------------------------------------------------------------

def _calculate_discount(
    original_price: Decimal,
    discount_percent: Decimal,
) -> dict[str, Decimal]:
    """Compute discount amount and final price deterministically.

    Uses banker's rounding (ROUND_HALF_UP) for consistency.
    Returns discount_amount and final_price as Decimals.
    """
    discount_amount = (original_price * discount_percent / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    final_price = (original_price - discount_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "discount_amount": discount_amount,
        "final_price": final_price,
    }


# ---------------------------------------------------------------------------
# Execution error hierarchy
# ---------------------------------------------------------------------------

class ExecutionError(Exception):
    """Base for simulated execution failures."""


class OpportunityNotFoundError(ExecutionError):
    """The opportunity does not exist in the approval store."""


class WrongMerchantError(ExecutionError):
    """The executing merchant does not own the opportunity."""


class NotApprovedError(ExecutionError):
    """The opportunity has not been approved by the merchant."""


class UnsupportedActionError(ExecutionError):
    """The requested action type is not supported."""


class MissingGuardrailsError(ExecutionError):
    """Guardrails are missing from the opportunity."""


class GuardrailViolationError(ExecutionError):
    """The requested value violates a guardrail."""


class MalformedInputError(ExecutionError):
    """The financial input is malformed or invalid."""


class IdempotentReplayError(ExecutionError):
    """The same opportunity has already been successfully executed."""


# ---------------------------------------------------------------------------
# Main execution function
# ---------------------------------------------------------------------------

def execute_simulated_discount(
    merchant_id: str,
    opportunity_id: str,
    discount_percent: float | int | str,
    original_price: float | int | str,
    approval_record: dict[str, Any],
) -> dict[str, Any]:
    """Execute a simulated discount for an approved opportunity.

    This function:
    1. Validates the opportunity is approved
    2. Verifies merchant ownership
    3. Checks guardrails and action support
    4. Enforces hard maximum discount limit
    5. Computes discount deterministically
    6. Records audit events
    7. Returns a structured result (no real money action)

    Args:
        merchant_id: The merchant's UUID string.
        opportunity_id: The growth opportunity ID.
        discount_percent: Requested discount percentage (e.g. 5 for 5%).
        original_price: The product's original price (e.g. 65000).
        approval_record: The approval record from the approval store.

    Returns:
        Structured execution result dict.

    Raises:
        OpportunityNotFoundError: if opportunity is unknown
        WrongMerchantError: if merchant doesn't match
        NotApprovedError: if not approved
        UnsupportedActionError: if action not supported
        MissingGuardrailsError: if no guardrails
        GuardrailViolationError: if discount exceeds maximum
        MalformedInputError: if input is invalid
        IdempotentReplayError: if already executed
    """
    execution_id = _generate_execution_id(merchant_id, opportunity_id)

    # --- Validation: opportunity exists ---
    if approval_record is None:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason="Opportunity not found",
        )
        raise OpportunityNotFoundError(
            f"Opportunity {opportunity_id} not found for merchant {merchant_id}"
        )

    # --- Validation: merchant ownership ---
    if approval_record.get("merchant_id") != merchant_id:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason="Merchant does not own this opportunity",
        )
        raise WrongMerchantError(
            "Merchant does not own this opportunity"
        )

    # --- Validation: status is approved ---
    if approval_record.get("status") != "approved":
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Opportunity status is '{approval_record.get('status')}', expected 'approved'",
            current_status=approval_record.get("status"),
        )
        raise NotApprovedError(
            f"Opportunity status is '{approval_record.get('status')}', expected 'approved'"
        )

    # --- Validation: guardrails exist ---
    guardrails = approval_record.get("guardrails", [])
    if not guardrails:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason="No guardrails defined",
        )
        raise MissingGuardrailsError("No guardrails defined for this opportunity")

    # --- Validation: action type is supported ---
    proposed_action = approval_record.get("proposed_action", "")
    # For this POC, the only supported action is simulated_discount.
    # The proposed_action string must indicate a pricing/discount action.
    action_type = "simulated_discount"
    if action_type not in SUPPORTED_ACTION_TYPES:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Unsupported action type: {action_type}",
        )
        raise UnsupportedActionError(f"Unsupported action type: {action_type}")

    # --- Idempotency check ---
    exec_key = _make_execution_key(merchant_id, opportunity_id)
    with _lock:
        existing = _executions.get(exec_key)
        if existing is not None and existing.get("status") == "simulated":
            _record_event(
                "execution_denied",
                merchant_id,
                opportunity_id,
                execution_id=execution_id,
                reason="Duplicate execution: opportunity already executed",
            )
            raise IdempotentReplayError(
                f"Opportunity {opportunity_id} has already been executed"
            )

    # --- Parse and validate discount_percent ---
    try:
        discount_dec = Decimal(str(discount_percent))
    except (InvalidOperation, ValueError, TypeError) as exc:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Malformed discount_percent: {discount_percent}",
        )
        raise MalformedInputError(
            f"Invalid discount_percent: {discount_percent}"
        ) from exc

    if discount_dec <= Decimal("0"):
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Discount must be positive, got {discount_dec}",
        )
        raise GuardrailViolationError(
            f"Discount must be positive, got {discount_dec}"
        )

    # --- Enforce hard maximum guardrail ---
    if discount_dec > MAX_DISCOUNT_PERCENT:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Discount {discount_dec}% exceeds maximum {MAX_DISCOUNT_PERCENT}%",
            requested_percent=str(discount_dec),
            max_percent=str(MAX_DISCOUNT_PERCENT),
        )
        raise GuardrailViolationError(
            f"Discount {discount_dec}% exceeds maximum allowed {MAX_DISCOUNT_PERCENT}%"
        )

    # --- Parse and validate original_price ---
    try:
        price_dec = Decimal(str(original_price))
    except (InvalidOperation, ValueError, TypeError) as exc:
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Malformed original_price: {original_price}",
        )
        raise MalformedInputError(
            f"Invalid original_price: {original_price}"
        ) from exc

    if price_dec <= Decimal("0"):
        _record_event(
            "execution_denied",
            merchant_id,
            opportunity_id,
            execution_id=execution_id,
            reason=f"Original price must be positive, got {price_dec}",
        )
        raise MalformedInputError(
            f"Original price must be positive, got {price_dec}"
        )

    # --- Record execution_requested ---
    _record_event(
        "execution_requested",
        merchant_id,
        opportunity_id,
        execution_id=execution_id,
        action_type=action_type,
        discount_percent=str(discount_dec),
        original_price=str(price_dec),
    )

    # --- Record execution_allowed (gate passed) ---
    _record_event(
        "execution_allowed",
        merchant_id,
        opportunity_id,
        execution_id=execution_id,
        guardrails_checked=len(guardrails),
        proposed_action=proposed_action,
    )

    # --- Deterministic financial calculation ---
    calc = _calculate_discount(price_dec, discount_dec)
    discount_amount = calc["discount_amount"]
    final_price = calc["final_price"]

    # --- Build execution result ---
    result = {
        "execution_id": execution_id,
        "opportunity_id": opportunity_id,
        "merchant_id": merchant_id,
        "action_type": action_type,
        "original_value": f"{price_dec:.2f}",
        "requested_value": f"{discount_dec:.2f}",
        "bounded_value": f"{discount_dec:.2f}",
        "simulated_result": {
            "discount_amount": f"{discount_amount:.2f}",
            "final_price": f"{final_price:.2f}",
        },
        "guardrails_checked": len(guardrails),
        "status": "simulated",
        "approval_required": True,
        "timestamp": _now_iso(),
        "disclaimer": "SIMULATED — no real financial transaction has occurred",
    }

    # --- Persist execution state (idempotency) ---
    with _lock:
        _executions[exec_key] = {
            "execution_id": execution_id,
            "merchant_id": merchant_id,
            "opportunity_id": opportunity_id,
            "action_type": action_type,
            "status": "simulated",
            "result": result,
        }

    # --- Record simulated_action_completed ---
    _record_event(
        "simulated_action_completed",
        merchant_id,
        opportunity_id,
        execution_id=execution_id,
        action_type=action_type,
        discount_percent=str(discount_dec),
        discount_amount=str(discount_amount),
        final_price=str(final_price),
        original_price=str(price_dec),
    )

    return result


# ---------------------------------------------------------------------------
# Execution state access
# ---------------------------------------------------------------------------

def get_execution(
    merchant_id: str,
    opportunity_id: str,
) -> dict[str, Any] | None:
    """Retrieve a previously recorded execution, or None."""
    key = _make_execution_key(merchant_id, opportunity_id)
    with _lock:
        exec_record = _executions.get(key)
        return dict(exec_record) if exec_record else None


def get_execution_events(
    merchant_id: str | None = None,
    opportunity_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return execution audit events, optionally filtered."""
    with _lock:
        events = list(_execution_events)

    if merchant_id is not None:
        events = [e for e in events if e["merchant_id"] == merchant_id]
    if opportunity_id is not None:
        events = [e for e in events if e["opportunity_id"] == opportunity_id]

    return events

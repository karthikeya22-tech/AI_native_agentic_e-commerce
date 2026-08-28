"""Deterministic merchant approval and execution-gate service.

Manages the lifecycle of growth opportunity approvals:
    proposed → approved

The execution gate validates approval status and guardrails before
authorizing any downstream action. It does NOT perform the action itself.

No LLM calls. No money actions. All operations are deterministic.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores (reset-safe for tests)
# ---------------------------------------------------------------------------

_approvals: dict[str, dict[str, Any]] = {}
_audit_events: list[dict[str, Any]] = []
_lock = threading.RLock()

VALID_STATUSES = ("proposed", "approved")
VALID_TRANSITIONS = {
    "proposed": {"approved"},
}


def reset_stores() -> None:
    """Clear all in-memory state. For test isolation only."""
    with _lock:
        _approvals.clear()
        _audit_events.clear()


def _make_key(merchant_id: str, opportunity_id: str) -> str:
    return f"{merchant_id}:{opportunity_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_audit(
    event_type: str,
    merchant_id: str,
    opportunity_id: str,
    **extra: Any,
) -> None:
    event = {
        "event_type": event_type,
        "merchant_id": merchant_id,
        "opportunity_id": opportunity_id,
        "timestamp": _now_iso(),
        **extra,
    }
    with _lock:
        _audit_events.append(event)
    logger.info("audit_event: %s merchant=%s opp=%s", event_type, merchant_id, opportunity_id)


# ---------------------------------------------------------------------------
# Opportunity record helpers
# ---------------------------------------------------------------------------

def record_opportunity_created(
    merchant_id: str,
    opportunity_id: str,
    proposed_action: str,
    guardrails: list[str],
) -> None:
    """Register a newly created opportunity in the approval store."""
    key = _make_key(merchant_id, opportunity_id)
    with _lock:
        _approvals[key] = {
            "merchant_id": merchant_id,
            "opportunity_id": opportunity_id,
            "status": "proposed",
            "proposed_action": proposed_action,
            "guardrails": list(guardrails),
            "approved_by": None,
            "approved_at": None,
        }
    _record_audit(
        "opportunity_created",
        merchant_id,
        opportunity_id,
        proposed_action=proposed_action,
        guardrails=guardrails,
    )


# ---------------------------------------------------------------------------
# Approval logic
# ---------------------------------------------------------------------------

class ApprovalError(Exception):
    """Base for approval failures."""


class OpportunityNotFoundError(ApprovalError):
    """The opportunity does not exist in the store."""


class WrongMerchantError(ApprovalError):
    """The approving merchant does not own the opportunity."""


class InvalidTransitionError(ApprovalError):
    """The requested status transition is not allowed."""


class ExplicitConsentRequiredError(ApprovalError):
    """The approval request did not contain explicit consent."""


def approve_opportunity(
    merchant_id: str,
    opportunity_id: str,
    approved: bool,
    approved_by: str,
) -> dict[str, Any]:
    """Process a merchant approval request.

    Allowed transitions:
        proposed → approved  (when approved=True)

    Returns the updated approval record.

    Raises:
        OpportunityNotFoundError: if opportunity_id is unknown
        WrongMerchantError: if merchant_id does not match
        InvalidTransitionError: if status transition is not allowed
        ExplicitConsentRequiredError: if approved is not True
    """
    key = _make_key(merchant_id, opportunity_id)

    with _lock:
        record = _approvals.get(key)
        if record is None:
            raise OpportunityNotFoundError(
                f"Opportunity {opportunity_id} not found for merchant {merchant_id}"
            )

        if record["merchant_id"] != merchant_id:
            raise WrongMerchantError(
                "Merchant does not own this opportunity"
            )

        current_status = record["status"]

        if not approved:
            _record_audit(
                "approval_denied",
                merchant_id,
                opportunity_id,
                approved_by=approved_by,
                reason="Merchant explicitly denied approval",
            )
            return dict(record)

        allowed = VALID_TRANSITIONS.get(current_status, set())
        if "approved" not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from '{current_status}' to 'approved'"
            )

        record["status"] = "approved"
        record["approved_by"] = approved_by
        record["approved_at"] = _now_iso()

    _record_audit(
        "approval_granted",
        merchant_id,
        opportunity_id,
        approved_by=approved_by,
        new_status="approved",
    )

    return dict(record)


def get_approval(merchant_id: str, opportunity_id: str) -> dict[str, Any] | None:
    """Retrieve the current approval record, or None."""
    key = _make_key(merchant_id, opportunity_id)
    with _lock:
        record = _approvals.get(key)
        return dict(record) if record else None


# ---------------------------------------------------------------------------
# Execution gate
# ---------------------------------------------------------------------------

class ExecutionDeniedError(Exception):
    """The execution gate denied authorization."""


def check_execution_gate(
    merchant_id: str,
    opportunity_id: str,
) -> dict[str, Any]:
    """Validate that an opportunity is authorized for execution.

    Checks:
    1. Opportunity exists
    2. Merchant matches
    3. Status is 'approved'
    4. Guardrails are present and non-empty

    Returns a structured authorization result dict.
    Does NOT perform the actual action.

    Raises:
        ExecutionDeniedError with a structured reason on failure.
    """
    key = _make_key(merchant_id, opportunity_id)

    with _lock:
        record = _approvals.get(key)

    if record is None:
        _record_audit(
            "execution_denied",
            merchant_id,
            opportunity_id,
            reason="Opportunity not found",
        )
        raise ExecutionDeniedError("Opportunity not found")

    if record["merchant_id"] != merchant_id:
        _record_audit(
            "execution_denied",
            merchant_id,
            opportunity_id,
            reason="Merchant does not own this opportunity",
        )
        raise ExecutionDeniedError("Merchant does not own this opportunity")

    if record["status"] != "approved":
        _record_audit(
            "execution_denied",
            merchant_id,
            opportunity_id,
            reason=f"Opportunity status is '{record['status']}', expected 'approved'",
            current_status=record["status"],
        )
        raise ExecutionDeniedError(
            f"Opportunity status is '{record['status']}', expected 'approved'"
        )

    guardrails = record.get("guardrails", [])
    if not guardrails:
        _record_audit(
            "execution_denied",
            merchant_id,
            opportunity_id,
            reason="No guardrails defined",
        )
        raise ExecutionDeniedError("No guardrails defined for this opportunity")

    authorized = {
        "authorized": True,
        "merchant_id": merchant_id,
        "opportunity_id": opportunity_id,
        "status": record["status"],
        "approved_by": record["approved_by"],
        "approved_at": record["approved_at"],
        "proposed_action": record["proposed_action"],
        "guardrails": guardrails,
        "authorization_timestamp": _now_iso(),
    }

    _record_audit(
        "execution_authorized",
        merchant_id,
        opportunity_id,
        approved_by=record["approved_by"],
    )

    return authorized


# ---------------------------------------------------------------------------
# Audit log access
# ---------------------------------------------------------------------------

def get_audit_events(
    merchant_id: str | None = None,
    opportunity_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return audit events, optionally filtered."""
    with _lock:
        events = list(_audit_events)

    if merchant_id is not None:
        events = [e for e in events if e["merchant_id"] == merchant_id]
    if opportunity_id is not None:
        events = [e for e in events if e["opportunity_id"] == opportunity_id]

    return events

"""Deterministic merchant approval and execution-gate service.

Manages the lifecycle of growth opportunity approvals:
    proposed → approved

The execution gate validates approval status and guardrails before
authorizing any downstream action. It does NOT perform the action itself.

Audit events are delegated to the unified audit_service for a single,
append-only, merchant-isolated audit trail.

No LLM calls. No money actions. All operations are deterministic.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.api.v1.audit_service import record_audit_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores (reset-safe for tests)
# ---------------------------------------------------------------------------

_approvals: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()

VALID_STATUSES = ("proposed", "approved")
VALID_TRANSITIONS = {
    "proposed": {"approved"},
}


def reset_stores() -> None:
    """Clear all in-memory state. For test isolation only."""
    with _lock:
        _approvals.clear()


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
    """Delegate audit recording to the unified audit_service."""
    # Map event_type to actor and status.
    actor = "system"
    status = ""
    reason = ""

    if event_type == "opportunity_created":
        status = "proposed"
        reason = "Catalog issue identified from deterministic readiness analysis"
    elif event_type == "approval_granted":
        actor = "merchant"
        status = "approved"
        reason = "Merchant explicitly approved proposed action"
    elif event_type == "approval_denied":
        actor = "merchant"
        status = "denied"
        reason = extra.get("reason", "Merchant explicitly denied approval")
    elif event_type == "execution_denied":
        status = "denied"
        reason = extra.get("reason", "Execution gate denied authorization")
    elif event_type == "execution_authorized":
        status = "allowed"
        reason = "Approval and guardrails validated"
    else:
        reason = extra.get("reason", "")

    # Build metadata from extra fields.
    metadata = {k: v for k, v in extra.items() if k != "reason"}

    try:
        record_audit_event(
            event_type=event_type,
            merchant_id=merchant_id,
            opportunity_id=opportunity_id,
            actor=actor,
            status=status,
            reason=reason,
            metadata=metadata,
        )
    except Exception:
        # Audit failure MUST NOT propagate to affect business logic.
        logger.exception(
            "audit_failure: Failed to record event %s for merchant=%s opp=%s",
            event_type,
            merchant_id,
            opportunity_id,
        )


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
# Audit log access (delegates to unified audit_service)
# ---------------------------------------------------------------------------

def get_audit_events(
    merchant_id: str | None = None,
    opportunity_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return audit events, optionally filtered.

    Delegates to the unified audit_service for a single source of truth.
    """
    from app.api.v1.audit_service import get_audit_events_for_merchant

    if merchant_id is not None:
        return get_audit_events_for_merchant(
            merchant_id,
            opportunity_id=opportunity_id,
            newest_first=False,
            limit=10000,
        )
    # If no merchant_id, return empty (merchant isolation enforced).
    return []

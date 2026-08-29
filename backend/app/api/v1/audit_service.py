"""Unified audit trail service for the agentic financial decision chain.

Provides a single, append-only, merchant-isolated audit store that captures
the complete lifecycle of growth opportunities:

    opportunity_created → approval_requested → approval_granted →
    execution_requested → execution_allowed → simulated_action_completed

Or on denial paths:

    execution_denied, approval_denied, llm_failure

Every audit event is:
- explainable (event_type, reason, metadata)
- append-only (never silently overwritten)
- merchant-isolated (cross-merchant access is impossible)
- secret-free (no API keys, passwords, prompts, or buyer PII)

No LLM calls. No money actions. All operations are deterministic.

Audit logging failure MUST NOT authorize a financial action.
If audit persistence fails, the action is safely denied.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Append-only audit store (reset-safe for tests)
# ---------------------------------------------------------------------------

_audit_events: list[dict[str, Any]] = []
_lock = threading.RLock()
_counter: int = 0

# Secrets and sensitive fields that must NEVER be stored in audit events.
_FORBIDDEN_KEYS = frozenset({
    "api_key", "api_keys", "secret", "password", "token",
    "authorization", "authorization_header", "bearer",
    "database_url", "database_password", "db_password",
    "llm_api_key", "llm_key", "openai_key", "openai_api_key",
    "supabase_key", "supabase_anon_key", "supabase_service_role_key",
    "full_prompt", "system_prompt", "prompt_template",
    "buyer_name", "buyer_email", "buyer_phone", "buyer_address",
    "buyer_ip", "credit_card", "card_number", "cvv",
})

# Known event types for validation.
VALID_EVENT_TYPES = frozenset({
    "opportunity_created",
    "approval_requested",
    "approval_granted",
    "approval_denied",
    "execution_requested",
    "execution_allowed",
    "execution_denied",
    "simulated_action_completed",
    "llm_failure",
})


def reset_audit_store() -> None:
    """Clear all audit events. For test isolation only."""
    global _counter
    with _lock:
        _audit_events.clear()
        _counter = 0


def _now_iso() -> str:
    """Return current UTC time with microsecond precision for ordering."""
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec="microseconds")


def _generate_event_id() -> str:
    """Generate a unique, non-deterministic audit event ID."""
    return uuid.uuid4().hex[:16]


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Remove any forbidden keys from metadata to prevent secret leakage."""
    sanitized = {}
    for key, value in metadata.items():
        if key.lower() in _FORBIDDEN_KEYS:
            logger.warning("audit_sanitize: removed forbidden key '%s'", key)
            continue
        sanitized[key] = value
    return sanitized


def _validate_event_type(event_type: str) -> None:
    """Warn if an unexpected event type is used (does not block)."""
    if event_type not in VALID_EVENT_TYPES:
        logger.warning(
            "audit_unexpected_event_type: '%s' not in known event types",
            event_type,
        )


# ---------------------------------------------------------------------------
# Core audit logging
# ---------------------------------------------------------------------------

def record_audit_event(
    event_type: str,
    merchant_id: str,
    opportunity_id: str,
    *,
    actor: str = "system",
    status: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a single audit event. Append-only; never modifies existing events.

    Args:
        event_type: One of VALID_EVENT_TYPES (e.g. "opportunity_created").
        merchant_id: The owning merchant's UUID string.
        opportunity_id: The growth opportunity ID.
        actor: Who initiated this event: "system", "merchant", or "agent".
        status: The status after this event (e.g. "proposed", "approved").
        reason: Human-readable explanation of why this event occurred.
        metadata: Additional structured data (sanitized of secrets).

    Returns:
        The recorded audit event dict with event_id and timestamp.
    """
    _validate_event_type(event_type)

    sanitized_meta = _sanitize_metadata(metadata) if metadata else {}

    with _lock:
        global _counter
        _counter += 1
        seq = _counter

    event = {
        "event_id": _generate_event_id(),
        "event_type": event_type,
        "merchant_id": merchant_id,
        "opportunity_id": opportunity_id,
        "timestamp": _now_iso(),
        "actor": actor,
        "status": status,
        "reason": reason,
        "metadata": sanitized_meta,
        "_seq": seq,
    }

    with _lock:
        # Store a copy with _seq for internal ordering.
        _audit_events.append(dict(event))

    logger.info(
        "audit: %s merchant=%s opp=%s actor=%s status=%s",
        event_type,
        merchant_id,
        opportunity_id,
        actor,
        status,
    )

    # Strip internal _seq before returning.
    event.pop("_seq", None)
    return event


# ---------------------------------------------------------------------------
# Audit event access
# ---------------------------------------------------------------------------

def get_audit_events_for_merchant(
    merchant_id: str,
    opportunity_id: str | None = None,
    *,
    newest_first: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Retrieve audit events for a specific merchant.

    Enforces strict merchant isolation: only events matching merchant_id
    are returned. Cross-merchant queries return empty.

    Args:
        merchant_id: The merchant to query events for.
        opportunity_id: Optional filter for a specific opportunity.
        newest_first: If True, return events newest-first (default).
        limit: Maximum number of events to return (default 100).
        offset: Number of events to skip for pagination (default 0).

    Returns:
        List of audit event dicts, ordered chronologically per newest_first.
    """
    with _lock:
        events = [dict(e) for e in _audit_events]

    # Strict merchant isolation.
    events = [e for e in events if e["merchant_id"] == merchant_id]

    # Optional opportunity filter.
    if opportunity_id is not None:
        events = [e for e in events if e["opportunity_id"] == opportunity_id]

    # Sort by sequence number (insertion order) with timestamp as secondary.
    events.sort(key=lambda e: (e.get("_seq", 0), e["timestamp"]), reverse=newest_first)

    # Strip internal _seq field before returning.
    for e in events:
        e.pop("_seq", None)

    # Apply pagination.
    events = events[offset : offset + limit]

    return events


def get_audit_trail_for_opportunity(
    merchant_id: str,
    opportunity_id: str,
) -> list[dict[str, Any]]:
    """Retrieve the complete lifecycle audit trail for a single opportunity.

    Returns events in chronological order (oldest first) to show the
    full decision chain from creation to final state.

    Enforces strict merchant isolation.

    Args:
        merchant_id: The owning merchant's UUID string.
        opportunity_id: The growth opportunity ID.

    Returns:
        List of audit event dicts in chronological order.

    Raises:
        ValueError: If no events exist for this merchant+opportunity.
    """
    with _lock:
        events = [dict(e) for e in _audit_events]

    # Strict merchant isolation.
    events = [e for e in events if e["merchant_id"] == merchant_id]
    events = [e for e in events if e["opportunity_id"] == opportunity_id]

    if not events:
        raise ValueError(
            f"No audit events found for merchant {merchant_id}, "
            f"opportunity {opportunity_id}"
        )

    # Chronological order (oldest first) by sequence number.
    events.sort(key=lambda e: (e.get("_seq", 0), e["timestamp"]))

    # Strip internal _seq field before returning.
    for e in events:
        e.pop("_seq", None)

    return events


def count_audit_events(merchant_id: str) -> int:
    """Count total audit events for a merchant."""
    with _lock:
        return sum(1 for e in _audit_events if e["merchant_id"] == merchant_id)


def has_audit_events(merchant_id: str, opportunity_id: str) -> bool:
    """Check if any audit events exist for a merchant+opportunity pair."""
    with _lock:
        return any(
            e["merchant_id"] == merchant_id and e["opportunity_id"] == opportunity_id
            for e in _audit_events
        )

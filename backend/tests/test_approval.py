"""Tests for merchant approval and gated execution.

Covers:
1. Approval succeeds (proposed → approved)
2. Approval requires explicit consent
3. Wrong merchant denied
4. Nonexistent opportunity → 404
5. Duplicate approval → deterministic response
6. Execution without approval denied
7. Execution with approval allowed by gate
8. Guardrail failure denied
9. Audit events generated
10. No money action is executed
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.api.v1.approval_service import (
    ApprovalError,
    ExecutionDeniedError,
    ExplicitConsentRequiredError,
    InvalidTransitionError,
    OpportunityNotFoundError,
    WrongMerchantError,
    approve_opportunity,
    check_execution_gate,
    get_approval,
    get_audit_events,
    record_opportunity_created,
    reset_stores,
)
from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product

MERCHANT_ID = uuid4()
OTHER_MERCHANT_ID = uuid4()

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fake DB infrastructure (matches existing test patterns)
# ---------------------------------------------------------------------------

class FakeDB:
    def __init__(self, merchant_result=None, product_results=None):
        self._results = {
            Merchant: merchant_result or [],
            Product: product_results or [],
        }

    def query(self, model):
        return _FakeQuery(self._results[model])


class _FakeQuery:
    def __init__(self, result):
        self.result = result
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def first(self):
        rows = self._filtered()
        return rows[0] if rows else None

    def all(self):
        return self._filtered()

    def _filtered(self):
        rows = self.result
        for crit in self.criteria:
            column = crit.left.key
            right = crit.right
            if isinstance(right, sql.elements.True_):
                value = True
            elif isinstance(right, sql.elements.False_):
                value = False
            else:
                value = right.value
            rows = [r for r in rows if getattr(r, column, None) == value]
        return rows


def make_product(**overrides) -> object:
    base = dict(
        id=uuid4(),
        merchant_id=MERCHANT_ID,
        name="Complete Widget",
        description="A fully specified widget with plenty of descriptive detail.",
        category="electronics",
        price=Decimal("999.00"),
        currency="INR",
        inventory_quantity=10,
        delivery_info={"eta_days": 3},
        return_policy="7-day returns",
        product_metadata={"brand": "TechKart"},
        is_active=True,
    )
    base.update(overrides)
    return type("FakeProduct", (), base)()


def override_db(fake_db: FakeDB) -> None:
    app.dependency_overrides[get_db] = lambda: fake_db


def setup_function():
    app.dependency_overrides.clear()
    reset_stores()


def teardown_function():
    app.dependency_overrides.clear()
    reset_stores()


def _seed_opportunity(merchant_id: str = None) -> str:
    """Create an opportunity in the approval store and return its ID."""
    mid = merchant_id or str(MERCHANT_ID)
    opp_id = "test_opp_abc123"
    record_opportunity_created(
        mid, opp_id, "Fix product descriptions", ["guardrail A", "guardrail B"]
    )
    return opp_id


# ---------------------------------------------------------------------------
# Unit tests: approval_service
# ---------------------------------------------------------------------------

class TestApprovalService:
    """Core approval logic."""

    def test_approve_succeeds(self):
        opp_id = _seed_opportunity()
        record = approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        assert record["status"] == "approved"
        assert record["approved_by"] == "merchant"
        assert record["approved_at"] is not None

    def test_approve_requires_explicit_consent(self):
        opp_id = _seed_opportunity()
        record = approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=False, approved_by="merchant"
        )
        # Status stays proposed when denied.
        assert record["status"] == "proposed"

    def test_wrong_merchant_denied(self):
        opp_id = _seed_opportunity(str(MERCHANT_ID))
        # Manually set the record's merchant_id to MERCHANT_ID but use OTHER_MERCHANT_ID for lookup.
        from app.api.v1.approval_service import _approvals, _lock, _make_key
        key = _make_key(str(MERCHANT_ID), opp_id)
        with _lock:
            _approvals[key]["merchant_id"] = str(OTHER_MERCHANT_ID)
        try:
            approve_opportunity(
                str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
            )
            assert False, "Should have raised"
        except WrongMerchantError:
            pass

    def test_nonexistent_opportunity(self):
        from app.api.v1.approval_service import OpportunityNotFoundError
        try:
            approve_opportunity(
                str(MERCHANT_ID), "does_not_exist", approved=True, approved_by="merchant"
            )
            assert False, "Should have raised"
        except OpportunityNotFoundError:
            pass

    def test_duplicate_approval_is_deterministic(self):
        opp_id = _seed_opportunity()
        r1 = approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        # Second call raises InvalidTransition because already approved.
        try:
            approve_opportunity(
                str(MERCHANT_ID), opp_id, approved=True, approved_by="admin"
            )
            assert False, "Should have raised"
        except InvalidTransitionError:
            pass
        # First call result is deterministic.
        assert r1["status"] == "approved"
        assert r1["approved_by"] == "merchant"

    def test_invalid_transition_already_approved(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        from app.api.v1.approval_service import InvalidTransitionError
        try:
            approve_opportunity(
                str(MERCHANT_ID), opp_id, approved=True, approved_by="admin"
            )
            assert False, "Should have raised"
        except InvalidTransitionError:
            pass

    def test_get_approval_returns_record(self):
        opp_id = _seed_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)
        assert record is not None
        assert record["status"] == "proposed"

    def test_get_approval_returns_none_for_unknown(self):
        record = get_approval(str(MERCHANT_ID), "nonexistent")
        assert record is None


# ---------------------------------------------------------------------------
# Unit tests: execution gate
# ---------------------------------------------------------------------------

class TestExecutionGate:
    """Execution gate authorization logic."""

    def test_execution_without_approval_denied(self):
        opp_id = _seed_opportunity()
        try:
            check_execution_gate(str(MERCHANT_ID), opp_id)
            assert False, "Should have raised"
        except ExecutionDeniedError as exc:
            assert "approved" in str(exc).lower()

    def test_execution_with_approval_allowed(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        auth = check_execution_gate(str(MERCHANT_ID), opp_id)
        assert auth["authorized"] is True
        assert auth["merchant_id"] == str(MERCHANT_ID)
        assert auth["opportunity_id"] == opp_id
        assert auth["status"] == "approved"
        assert auth["approved_by"] == "merchant"
        assert auth["proposed_action"] == "Fix product descriptions"
        assert len(auth["guardrails"]) == 2

    def test_execution_wrong_merchant_denied(self):
        opp_id = _seed_opportunity(str(MERCHANT_ID))
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        # Manually change the record's merchant_id so it doesn't match the lookup.
        from app.api.v1.approval_service import _approvals, _lock, _make_key
        key = _make_key(str(MERCHANT_ID), opp_id)
        with _lock:
            _approvals[key]["merchant_id"] = str(OTHER_MERCHANT_ID)
        try:
            check_execution_gate(str(MERCHANT_ID), opp_id)
            assert False, "Should have raised"
        except ExecutionDeniedError as exc:
            assert "does not own" in str(exc).lower()

    def test_execution_nonexistent_opportunity(self):
        try:
            check_execution_gate(str(MERCHANT_ID), "nonexistent")
            assert False, "Should have raised"
        except ExecutionDeniedError as exc:
            assert "not found" in str(exc).lower()

    def test_execution_no_guardrails_denied(self):
        """Manually insert a record with empty guardrails."""
        from app.api.v1.approval_service import _approvals, _lock, _make_key
        key = _make_key(str(MERCHANT_ID), "no_guardrails_opp")
        with _lock:
            _approvals[key] = {
                "merchant_id": str(MERCHANT_ID),
                "opportunity_id": "no_guardrails_opp",
                "status": "approved",
                "proposed_action": "Do something",
                "guardrails": [],
                "approved_by": "merchant",
                "approved_at": "2026-01-01T00:00:00+00:00",
            }
        try:
            check_execution_gate(str(MERCHANT_ID), "no_guardrails_opp")
            assert False, "Should have raised"
        except ExecutionDeniedError as exc:
            assert "guardrail" in str(exc).lower()


# ---------------------------------------------------------------------------
# Unit tests: audit events
# ---------------------------------------------------------------------------

class TestAuditEvents:
    """Audit events are generated for all state changes."""

    def test_opportunity_created_event(self):
        opp_id = _seed_opportunity()
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "opportunity_created" in types

    def test_approval_granted_event(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "approval_granted" in types

    def test_approval_denied_event(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=False, approved_by="merchant"
        )
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "approval_denied" in types

    def test_execution_denied_event(self):
        opp_id = _seed_opportunity()
        try:
            check_execution_gate(str(MERCHANT_ID), opp_id)
        except ExecutionDeniedError:
            pass
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "execution_denied" in types

    def test_execution_authorized_event(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        check_execution_gate(str(MERCHANT_ID), opp_id)
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "execution_authorized" in types

    def test_audit_events_have_timestamps(self):
        opp_id = _seed_opportunity()
        events = get_audit_events(str(MERCHANT_ID), opp_id)
        for e in events:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)


# ---------------------------------------------------------------------------
# HTTP endpoint tests: approval
# ---------------------------------------------------------------------------

class TestApprovalEndpoint:
    """POST /merchants/{id}/growth-opportunities/{opp_id}/approve"""

    def _seed_via_endpoint(self):
        """Generate opportunities via the API so they're registered in the store."""
        products = [
            make_product(description="", product_metadata=None),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))
        resp = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        return resp.json()["opportunities"]

    def test_approval_succeeds(self):
        opps = self._seed_via_endpoint()
        opp_id = opps[0]["opportunity_id"]

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
            json={"approved": True, "approved_by": "merchant"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["approved_by"] == "merchant"
        assert body["opportunity_id"] == opp_id
        assert body["merchant_id"] == str(MERCHANT_ID)
        assert body["approved_at"] is not None
        assert len(body["guardrails"]) > 0

    def test_approval_requires_explicit_consent(self):
        opps = self._seed_via_endpoint()
        opp_id = opps[0]["opportunity_id"]

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
            json={"approved": False, "approved_by": "merchant"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "proposed"
        assert body["approved_by"] is None

    def test_nonexistent_opportunity_returns_404(self):
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=[],
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/nonexistent/approve",
            json={"approved": True, "approved_by": "merchant"},
        )

        assert response.status_code == 404

    def test_wrong_merchant_returns_404(self):
        opps = self._seed_via_endpoint()
        opp_id = opps[0]["opportunity_id"]

        response = client.post(
            f"/api/v1/merchants/{OTHER_MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
            json={"approved": True, "approved_by": "merchant"},
        )

        assert response.status_code == 404

    def test_duplicate_approval_returns_409(self):
        opps = self._seed_via_endpoint()
        opp_id = opps[0]["opportunity_id"]

        client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
            json={"approved": True, "approved_by": "merchant"},
        )

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
            json={"approved": True, "approved_by": "admin"},
        )

        assert response.status_code == 409


# ---------------------------------------------------------------------------
# HTTP endpoint tests: growth-opportunities records in approval store
# ---------------------------------------------------------------------------

class TestOpportunityRegistration:
    """Growth opportunities are registered in the approval store."""

    def test_opportunities_registered_on_generation(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        resp = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        opps = resp.json()["opportunities"]

        for opp in opps:
            record = get_approval(str(MERCHANT_ID), opp["opportunity_id"])
            assert record is not None
            assert record["status"] == "proposed"

    def test_no_opportunities_no_registration(self):
        products = [make_product()]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        resp = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        assert resp.json()["opportunities"] == []


# ---------------------------------------------------------------------------
# No money action test
# ---------------------------------------------------------------------------

class TestNoMoneyAction:
    """Approval and gate never execute money actions."""

    def test_approval_only_changes_status(self):
        opp_id = _seed_opportunity()
        record = approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        # Only status, approved_by, approved_at change.
        assert record["proposed_action"] == "Fix product descriptions"
        assert record["guardrails"] == ["guardrail A", "guardrail B"]

    def test_execution_gate_returns_authorization_not_action(self):
        opp_id = _seed_opportunity()
        approve_opportunity(
            str(MERCHANT_ID), opp_id, approved=True, approved_by="merchant"
        )
        auth = check_execution_gate(str(MERCHANT_ID), opp_id)
        assert auth["authorized"] is True
        assert "action_executed" not in auth
        assert "price_change" not in auth
        assert "discount" not in auth

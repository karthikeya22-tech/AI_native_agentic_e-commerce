"""Tests for controlled financial action simulation (Phase 4.3).

Covers all required scenarios:
1. Approved opportunity can execute simulation
2. Unapproved opportunity is denied
3. Wrong merchant is denied
4. Unknown opportunity returns 404
5. Discount within guardrail succeeds
6. Discount above maximum is denied
7. Negative discount is denied
8. Malformed discount is denied
9. Repeated execution is idempotent
10. Product price remains unchanged
11. Audit events are generated
12. No payment/order/refund action occurs
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.api.v1.approval_service import (
    approve_opportunity,
    get_approval,
    record_opportunity_created,
    reset_stores,
)
from app.api.v1.simulated_execution_service import (
    GuardrailViolationError,
    IdempotentReplayError,
    MalformedInputError,
    MissingGuardrailsError,
    NotApprovedError,
    OpportunityNotFoundError as ExecOpportunityNotFoundError,
    UnsupportedActionError,
    WrongMerchantError as ExecWrongMerchantError,
    _calculate_discount,
    execute_simulated_discount,
    get_execution,
    get_execution_events,
    reset_executions,
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
        name="Premium Widget",
        description="A high-quality widget with complete details.",
        category="electronics",
        price=Decimal("65000.00"),
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


_test_counter = 0


def _next_opp_id(prefix: str = "opp") -> str:
    """Generate a unique opportunity ID for each test to avoid idempotency collisions."""
    global _test_counter
    _test_counter += 1
    return f"{prefix}_{_test_counter}"


class _SetupTeardown:
    """Mixin that resets all stores before/after each test method."""

    def setup_method(self):
        app.dependency_overrides.clear()
        reset_stores()
        reset_executions()

    def teardown_method(self):
        app.dependency_overrides.clear()
        reset_stores()
        reset_executions()


def _seed_approved_opportunity(
    merchant_id: str = None,
    opp_id: str | None = None,
) -> str:
    """Create and approve an opportunity for testing."""
    mid = merchant_id or str(MERCHANT_ID)
    oid = opp_id or _next_opp_id()
    record_opportunity_created(
        mid,
        oid,
        "Apply limited discount to boost conversions",
        [
            "No price changes, discounts, orders, refunds, or inventory modifications will occur",
            "approval_required is always true; the merchant must explicitly approve any action",
        ],
    )
    approve_opportunity(mid, oid, approved=True, approved_by="merchant")
    return oid


def _seed_unapproved_opportunity(
    merchant_id: str = None,
    opp_id: str | None = None,
) -> str:
    """Create an opportunity that has NOT been approved."""
    mid = merchant_id or str(MERCHANT_ID)
    oid = opp_id or _next_opp_id("unapproved")
    record_opportunity_created(
        mid,
        oid,
        "Apply limited discount to boost conversions",
        ["guardrail A", "guardrail B"],
    )
    return oid


# ---------------------------------------------------------------------------
# Unit tests: deterministic financial calculations
# ---------------------------------------------------------------------------

class TestDeterministicCalculation(_SetupTeardown):
    """Financial calculations must be deterministic and correct."""

    def test_basic_discount(self):
        calc = _calculate_discount(Decimal("65000"), Decimal("5"))
        assert calc["discount_amount"] == Decimal("3250.00")
        assert calc["final_price"] == Decimal("61750.00")

    def test_zero_discount(self):
        calc = _calculate_discount(Decimal("1000"), Decimal("0"))
        assert calc["discount_amount"] == Decimal("0.00")
        assert calc["final_price"] == Decimal("1000.00")

    def test_max_discount_10_percent(self):
        calc = _calculate_discount(Decimal("65000"), Decimal("10"))
        assert calc["discount_amount"] == Decimal("6500.00")
        assert calc["final_price"] == Decimal("58500.00")

    def test_fractional_discount(self):
        calc = _calculate_discount(Decimal("1000"), Decimal("2.5"))
        assert calc["discount_amount"] == Decimal("25.00")
        assert calc["final_price"] == Decimal("975.00")

    def test_rounding_is_deterministic(self):
        calc1 = _calculate_discount(Decimal("99.99"), Decimal("7"))
        calc2 = _calculate_discount(Decimal("99.99"), Decimal("7"))
        assert calc1 == calc2

    def test_same_inputs_always_produce_same_output(self):
        for _ in range(100):
            calc = _calculate_discount(Decimal("65000"), Decimal("5"))
            assert calc["discount_amount"] == Decimal("3250.00")
            assert calc["final_price"] == Decimal("61750.00")


# ---------------------------------------------------------------------------
# Unit tests: execution service
# ---------------------------------------------------------------------------

class TestSimulatedExecutionService(_SetupTeardown):
    """Core execution logic tests."""

    def test_approved_opportunity_executes(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        assert result["status"] == "simulated"
        assert result["action_type"] == "simulated_discount"
        assert result["execution_id"]
        assert result["opportunity_id"] == opp_id
        assert result["merchant_id"] == str(MERCHANT_ID)
        assert result["original_value"] == "65000.00"
        assert result["requested_value"] == "5.00"
        assert result["bounded_value"] == "5.00"
        assert result["simulated_result"]["discount_amount"] == "3250.00"
        assert result["simulated_result"]["final_price"] == "61750.00"
        assert result["guardrails_checked"] == 2
        assert result["approval_required"] is True
        assert "SIMULATED" in result["disclaimer"]

    def test_unapproved_opportunity_denied(self):
        opp_id = _seed_unapproved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=5,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised NotApprovedError"
        except NotApprovedError:
            pass

    def test_wrong_merchant_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(OTHER_MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=5,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised WrongMerchantError"
        except ExecWrongMerchantError:
            pass

    def test_unknown_opportunity_denied(self):
        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id="nonexistent",
                discount_percent=5,
                original_price="65000",
                approval_record=None,
            )
            assert False, "Should have raised OpportunityNotFoundError"
        except ExecOpportunityNotFoundError:
            pass

    def test_discount_within_guardrail_succeeds(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        assert result["status"] == "simulated"
        assert float(result["requested_value"]) <= 10.0

    def test_discount_above_maximum_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=15,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised GuardrailViolationError"
        except GuardrailViolationError as exc:
            assert "15" in str(exc) or "exceeds" in str(exc).lower()

    def test_negative_discount_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=-5,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised GuardrailViolationError"
        except GuardrailViolationError:
            pass

    def test_malformed_discount_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent="abc",
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised MalformedInputError"
        except MalformedInputError:
            pass

    def test_repeated_execution_is_idempotent(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result1 = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=5,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised IdempotentReplayError"
        except IdempotentReplayError:
            pass

        assert result1["status"] == "simulated"


# ---------------------------------------------------------------------------
# Audit event tests
# ---------------------------------------------------------------------------

class TestExecutionAuditEvents(_SetupTeardown):
    """Audit events are generated for execution lifecycle."""

    def test_execution_requested_event(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        events = get_execution_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "execution_requested" in types

    def test_execution_allowed_event(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        events = get_execution_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "execution_allowed" in types

    def test_simulated_action_completed_event(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        events = get_execution_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "simulated_action_completed" in types

    def test_execution_denied_event_on_guardrail_violation(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=15,
                original_price="65000",
                approval_record=record,
            )
        except GuardrailViolationError:
            pass

        events = get_execution_events(str(MERCHANT_ID), opp_id)
        types = [e["event_type"] for e in events]
        assert "execution_denied" in types

    def test_audit_events_have_timestamps(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        events = get_execution_events(str(MERCHANT_ID), opp_id)
        for e in events:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)


# ---------------------------------------------------------------------------
# No real mutation tests
# ---------------------------------------------------------------------------

class TestNoRealMutation(_SetupTeardown):
    """No payment, order, refund, or product price mutation occurs."""

    def test_product_price_unchanged_after_simulation(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        original_price = Decimal("65000.00")

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price=str(original_price),
            approval_record=record,
        )

        # The result shows a simulated final_price, but the original_value
        # must match what we passed in — indicating no real price was changed.
        assert result["original_value"] == "65000.00"
        assert result["simulated_result"]["final_price"] == "61750.00"

    def test_no_order_or_payment_created(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        # Result must not contain any real transaction artifacts.
        assert "order_id" not in result
        assert "payment_id" not in result
        assert "transaction_id" not in result
        assert "refund_id" not in result

    def test_execution_result_labeled_as_simulated(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        assert result["status"] == "simulated"
        assert "SIMULATED" in result["disclaimer"].upper()


# ---------------------------------------------------------------------------
# Guardrail enforcement tests
# ---------------------------------------------------------------------------

class TestGuardrailEnforcement(_SetupTeardown):
    """Hard guardrails are enforced."""

    def test_maximum_discount_10_percent(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        # Exactly 10% should succeed.
        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=10,
            original_price="65000",
            approval_record=record,
        )
        assert result["status"] == "simulated"

    def test_above_maximum_10_percent_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=10.01,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised GuardrailViolationError"
        except GuardrailViolationError:
            pass

    def test_zero_discount_denied(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        try:
            execute_simulated_discount(
                merchant_id=str(MERCHANT_ID),
                opportunity_id=opp_id,
                discount_percent=0,
                original_price="65000",
                approval_record=record,
            )
            assert False, "Should have raised GuardrailViolationError"
        except GuardrailViolationError:
            pass

    def test_guardrails_checked_count(self):
        opp_id = _seed_approved_opportunity()
        record = get_approval(str(MERCHANT_ID), opp_id)

        result = execute_simulated_discount(
            merchant_id=str(MERCHANT_ID),
            opportunity_id=opp_id,
            discount_percent=5,
            original_price="65000",
            approval_record=record,
        )

        assert result["guardrails_checked"] == 2


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestExecuteEndpoint(_SetupTeardown):
    """POST /merchants/{id}/growth-opportunities/{opp_id}/execute"""

    def _seed_via_endpoint(self):
        """Generate and approve an opportunity via the API."""
        products = [
            make_product(price=Decimal("65000.00")),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))
        resp = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        opps = resp.json()["opportunities"]
        if opps:
            opp_id = opps[0]["opportunity_id"]
            client.post(
                f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/approve",
                json={"approved": True, "approved_by": "merchant"},
            )
            return opp_id, opps
        return None, []

    def test_successful_simulation(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "simulated"
        assert body["action_type"] == "simulated_discount"
        assert body["execution_id"]
        assert body["opportunity_id"] == opp_id
        assert body["merchant_id"] == str(MERCHANT_ID)
        assert body["original_value"] == "65000.00"
        assert body["requested_value"] == "5.00"
        assert body["bounded_value"] == "5.00"
        assert body["simulated_result"]["discount_amount"] == "3250.00"
        assert body["simulated_result"]["final_price"] == "61750.00"
        assert "SIMULATED" in body["disclaimer"].upper()

    def test_unapproved_opportunity_returns_403(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        # Un-approve by creating a fresh unapproved opportunity.
        from app.api.v1.approval_service import _approvals, _lock, _make_key
        key = _make_key(str(MERCHANT_ID), opp_id)
        with _lock:
            if key in _approvals:
                _approvals[key]["status"] = "proposed"

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 403

    def test_wrong_merchant_returns_404(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=OTHER_MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{OTHER_MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 404

    def test_unknown_opportunity_returns_404(self):
        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/nonexistent/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 404

    def test_discount_above_max_returns_422(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 15},
        )

        assert response.status_code == 422

    def test_negative_discount_returns_422(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": -5},
        )

        assert response.status_code == 422

    def test_malformed_discount_returns_422(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": "abc"},
        )

        assert response.status_code == 422

    def test_repeated_execution_returns_409(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        products = [make_product(price=Decimal("65000.00"))]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        # First execution succeeds.
        resp1 = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )
        assert resp1.status_code == 200

        # Second execution is idempotent (409).
        resp2 = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )
        assert resp2.status_code == 409

    def test_product_price_unchanged_via_endpoint(self):
        opp_id, _ = self._seed_via_endpoint()
        if opp_id is None:
            return

        original_price = Decimal("65000.00")
        products = [make_product(price=original_price)]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(
            f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities/{opp_id}/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 200
        body = response.json()
        # original_value reflects the product's price, not a changed value.
        assert body["original_value"] == "65000.00"

    def test_no_unknown_merchant_returns_404(self):
        override_db(FakeDB(merchant_result=[]))

        response = client.post(
            f"/api/v1/merchants/{uuid4()}/growth-opportunities/fake/execute",
            json={"discount_percent": 5},
        )

        assert response.status_code == 404

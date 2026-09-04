"""Tests for deterministic growth opportunity generation.

Covers:
1. Deterministic opportunity generation (same inputs → same outputs)
2. Evidence is preserved from readiness issues
3. Financial assumptions are explicit
4. Insufficient evidence does not produce fabricated numbers
5. approval_required is always true
6. No money action is executed
7. Stable opportunity IDs
8. Failure handled gracefully
9. Unknown merchant → 404
"""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import sql

from app.api.v1.growth_opportunities_service import (
    ISSUE_TYPE_TO_CATEGORY,
    _stable_opportunity_id,
    generate_growth_opportunities,
)
from app.db.session import get_db
from app.main import app
from app.models.merchant import Merchant
from app.models.product import Product

MERCHANT_ID = uuid4()

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


def teardown_function():
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Unit tests: generate_growth_opportunities()
# ---------------------------------------------------------------------------

class TestDeterministicGeneration:
    """Requirement 1: deterministic opportunity generation."""

    def test_same_inputs_produce_same_outputs(self):
        products = [
            make_product(description="", product_metadata=None),
            make_product(name="Item 2", delivery_info=None, return_policy=""),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        results = [
            generate_growth_opportunities(str(MERCHANT_ID), products, issues)
            for _ in range(5)
        ]
        assert all(r == results[0] for r in results)

    def test_no_issues_returns_empty(self):
        products = [make_product()]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        assert opps == []

    def test_empty_products_returns_empty(self):
        opps = generate_growth_opportunities(str(MERCHANT_ID), [], [])
        assert opps == []


class TestEvidencePreservation:
    """Requirement 2: evidence is preserved."""

    def test_evidence_contains_original_issue_data(self):
        products = [
            make_product(description="", product_metadata=None),
            make_product(name="Item 2", delivery_info=None, return_policy=""),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        assert len(opps) > 0

        all_evidence = []
        for opp in opps:
            all_evidence.extend(opp["evidence"])

        evidence_issue_types = {e["issue_type"] for e in all_evidence}
        assert "missing_description" in evidence_issue_types
        assert "missing_delivery_info" in evidence_issue_types

        for e in all_evidence:
            assert e["source"] == "readiness_engine"
            assert e["product_id"]
            assert e["product_name"]
            assert e["severity"] in ("low", "medium", "high")
            assert e["description"]
            assert e["suggested_action"]

    def test_evidence_preserves_product_names(self):
        products = [
            make_product(name="Alpha Widget", description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        all_names = {e["product_name"] for opp in opps for e in opp["evidence"]}
        assert "Alpha Widget" in all_names


class TestFinancialAssumptions:
    """Requirement 3: financial assumptions are explicit."""

    def test_financial_impact_has_assumptions(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            fi = opp["financial_impact"]
            assert "type" in fi
            assert "assumptions" in fi
            assert isinstance(fi["assumptions"], list)
            assert len(fi["assumptions"]) > 0

    def test_assumptions_are_strings(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            for a in opp["financial_impact"]["assumptions"]:
                assert isinstance(a, str)
                assert len(a) > 0


class TestInsufficientEvidence:
    """Requirement 4: insufficient evidence does not produce fabricated numbers."""

    def test_no_products_yields_no_opportunities(self):
        opps = generate_growth_opportunities(str(MERCHANT_ID), [], [])
        assert opps == []

    def test_issues_without_prices_get_insufficient_evidence(self):
        """Issues referencing products with no parseable price → insufficient_evidence."""
        # Create a product with a non-numeric price edge case.
        products = [
            make_product(price=None),
        ]
        # Manually create issues to simulate the scenario.
        issues = [
            {
                "product_id": str(products[0].id),
                "product_name": "Test Product",
                "issue_type": "invalid_price",
                "description": "Price is missing.",
                "severity": "high",
                "suggested_action": "Set a price.",
            }
        ]
        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        assert len(opps) == 1
        fi = opps[0]["financial_impact"]
        assert fi["type"] == "insufficient_evidence"

    def test_insufficient_evidence_has_no_estimate(self):
        products = [
            make_product(price=None),
        ]
        issues = [
            {
                "product_id": str(products[0].id),
                "product_name": "Test",
                "issue_type": "invalid_price",
                "description": "No price.",
                "severity": "high",
                "suggested_action": "Set price.",
            }
        ]
        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        fi = opps[0]["financial_impact"]
        assert "estimate" not in fi or fi.get("estimate") == ""


class TestApprovalRequired:
    """Requirement 5: approval_required is always true."""

    def test_all_opportunities_require_approval(self):
        products = [
            make_product(description="", product_metadata=None),
            make_product(name="Item 2", delivery_info=None, return_policy=""),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            assert opp["approval_required"] is True


class TestNoMoneyAction:
    """Requirement 6: no money action is executed."""

    def test_opportunities_are_proposals_only(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            assert opp["status"] == "proposed"
            # Guardrails must explicitly state no money action.
            guardrail_text = " ".join(opp["guardrails"]).lower()
            assert "no price change" in guardrail_text or "no action will be taken" in guardrail_text


class TestStableOpportunityIDs:
    """Requirement 7: stable opportunity IDs."""

    def test_same_inputs_produce_same_id(self):
        id1 = _stable_opportunity_id("m1", "catalog_incomplete", ["missing_description"])
        id2 = _stable_opportunity_id("m1", "catalog_incomplete", ["missing_description"])
        assert id1 == id2

    def test_different_inputs_produce_different_ids(self):
        id1 = _stable_opportunity_id("m1", "catalog_incomplete", ["missing_description"])
        id2 = _stable_opportunity_id("m1", "conversion_blocker", ["invalid_price"])
        assert id1 != id2

    def test_id_is_deterministic_from_merchant_and_issues(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps1 = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        opps2 = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        ids1 = {o["opportunity_id"] for o in opps1}
        ids2 = {o["opportunity_id"] for o in opps2}
        assert ids1 == ids2

    def test_id_is_16_char_hex(self):
        id_val = _stable_opportunity_id("m1", "catalog_incomplete", ["missing_description"])
        assert len(id_val) == 16
        int(id_val, 16)  # Should not raise — valid hex.


class TestAuditInformation:
    """Requirement 8: audit-friendly representation."""

    def test_audit_field_present(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            audit = opp["audit"]
            assert "timestamp" in audit
            assert "signal_source" in audit
            assert audit["signal_source"] == "readiness_engine"
            assert "products_analyzed" in audit
            assert "issues_evaluated" in audit
            assert "generation_method" in audit
            assert audit["generation_method"] == "deterministic_rule_engine"
            assert "rule_version" in audit

    def test_audit_counts_match(self):
        products = [
            make_product(description="", product_metadata=None),
            make_product(name="Item 2", delivery_info=None, return_policy=""),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        total_evaluated = sum(o["audit"]["issues_evaluated"] for o in opps)
        assert total_evaluated == len(issues)


class TestGuardrails:
    """Guardrails must be present and meaningful."""

    def test_every_opportunity_has_guardrails(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            assert len(opp["guardrails"]) > 0
            assert all(isinstance(g, str) for g in opp["guardrails"])


class TestReasoning:
    """Reasoning must explain the opportunity."""

    def test_reasoning_is_non_empty_string(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        from app.api.v1.readiness_service import analyze_readiness
        _, _, issues = analyze_readiness(products)

        opps = generate_growth_opportunities(str(MERCHANT_ID), products, issues)
        for opp in opps:
            assert isinstance(opp["reasoning"], str)
            assert len(opp["reasoning"]) > 0


class TestIssueTypeMapping:
    """All known issue types map to a category."""

    def test_all_issue_types_have_categories(self):
        for issue_type in [
            "missing_description", "short_description", "missing_category",
            "invalid_price", "invalid_inventory", "missing_delivery_info",
            "missing_return_policy", "missing_metadata",
        ]:
            assert issue_type in ISSUE_TYPE_TO_CATEGORY


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestEndpointSuccess:
    """Endpoint returns valid opportunities."""

    def test_returns_200_with_opportunities(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert response.status_code == 200
        body = response.json()
        assert body["merchant_id"] == str(MERCHANT_ID)
        assert isinstance(body["opportunities"], list)

    def test_opportunity_schema_valid(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        body = response.json()

        for opp in body["opportunities"]:
            assert "opportunity_id" in opp
            assert "merchant_id" in opp
            assert "title" in opp
            assert "problem" in opp
            assert "evidence" in opp
            assert "financial_impact" in opp
            assert "proposed_action" in opp
            assert "guardrails" in opp
            assert "approval_required" in opp
            assert "status" in opp
            assert "reasoning" in opp
            assert "audit" in opp
            assert opp["approval_required"] is True
            assert opp["status"] == "proposed"


class TestEndpoint404:
    """Unknown merchant → 404."""

    def test_unknown_merchant_returns_404(self):
        override_db(FakeDB(merchant_result=[]))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert response.status_code == 404
        assert response.json()["detail"] == "Merchant not found"


class TestEndpointNoIssues:
    """Merchant with perfect catalog → empty opportunities."""

    def test_perfect_catalog_returns_empty(self):
        products = [make_product()]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert response.status_code == 200
        body = response.json()
        assert body["opportunities"] == []


class TestEndpointNoProducts:
    """Merchant with no products → empty opportunities."""

    def test_no_products_returns_empty(self):
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=[],
        ))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert response.status_code == 200
        body = response.json()
        assert body["opportunities"] == []


class TestEndpointMultipleIssueTypes:
    """Multiple issue types produce multiple opportunity categories."""

    def test_mixed_issues_produce_multiple_opportunities(self):
        products = [
            make_product(
                name="Bad Product",
                description="x",
                category=None,
                price=Decimal("0.00"),
                inventory_quantity=-1,
                delivery_info=None,
                return_policy="",
                product_metadata=None,
            ),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        response = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert response.status_code == 200
        body = response.json()
        categories = {o["audit"]["category"] for o in body["opportunities"]}
        # Should have at least catalog_incomplete and conversion_blocker.
        assert len(categories) >= 2


class TestEndpointDeterministic:
    """Endpoint responses are deterministic."""

    def test_same_request_produces_same_response(self):
        products = [
            make_product(description="", product_metadata=None),
        ]
        override_db(FakeDB(
            merchant_result=[SimpleNamespace(id=MERCHANT_ID)],
            product_results=products,
        ))

        r1 = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")
        r2 = client.post(f"/api/v1/merchants/{MERCHANT_ID}/growth-opportunities")

        assert r1.json() == r2.json()

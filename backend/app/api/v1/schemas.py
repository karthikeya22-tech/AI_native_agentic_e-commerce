from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


from app.models.merchant import MerchantStatus


class MerchantOnboardingRequest(BaseModel):
    email: EmailStr
    name: str
    category: str
    description: str | None = None


class MerchantOnboardingResponse(BaseModel):
    user_id: str
    merchant_id: str
    name: str
    status: str


class MerchantSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    description: str | None = None
    status: MerchantStatus


class ProductCreate(BaseModel):
    name: str
    description: str
    category: str
    price: Decimal = Field(ge=0)
    currency: str = "INR"
    inventory_quantity: int = Field(default=0, ge=0)
    delivery_info: dict | None = None
    return_policy: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    category: str
    price: Decimal
    currency: str
    inventory_quantity: int
    delivery_info: dict | None = None
    return_policy: str | None = None
    is_active: bool
    created_at: datetime


class ReadinessIssue(BaseModel):
    product_id: str
    product_name: str
    issue_type: str
    description: str
    severity: Literal["low", "medium", "high"]
    suggested_action: str


class ReadinessResponse(BaseModel):
    merchant_id: str
    overall_score: int
    products_analyzed: int
    issues_count: int
    issues: list[ReadinessIssue]


class GrowthRecommendation(BaseModel):
    title: str
    explanation: str
    suggested_action: str
    expected_impact: str
    priority: Literal["low", "medium", "high"]


class GrowthRecommendationsResponse(BaseModel):
    merchant_id: str
    recommendations: list[GrowthRecommendation]


class BuyerIntentRequest(BaseModel):
    message: str = Field(min_length=1)


class BuyerIntentResponse(BaseModel):
    category: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    use_case: str | None = None
    requirements: list[str] = []
    preferences: list[str] = []
    brand: str | None = None
    intent_source: Literal["llm", "deterministic_fallback"] = "llm"


class BuyerSearchRequest(BaseModel):
    merchant_id: UUID
    category: str | None = None
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    use_case: str | None = None
    requirements: list[str] = []
    preferences: list[str] = []
    brand: str | None = None

    @model_validator(mode="after")
    def check_budget_range(self):
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min must not exceed budget_max")
        return self


class BuyerSearchResultItem(BaseModel):
    product_id: UUID
    name: str
    description: str
    category: str
    price: str
    currency: str
    inventory_quantity: int
    similarity: float


class BuyerSearchResponse(BaseModel):
    results: list[BuyerSearchResultItem]


class OpportunityEvidence(BaseModel):
    source: str
    issue_type: str
    product_id: str
    product_name: str
    severity: Literal["low", "medium", "high"]
    description: str
    suggested_action: str


class FinancialImpact(BaseModel):
    type: str
    direction: str = "positive"
    estimate: str
    assumptions: list[str]


class AuditInfo(BaseModel):
    timestamp: str
    signal_source: str
    products_analyzed: int
    issues_evaluated: int
    generation_method: str
    rule_version: str
    affected_product_ids: list[str] = []
    category: str
    highest_severity: Literal["low", "medium", "high"]


class GrowthOpportunity(BaseModel):
    opportunity_id: str
    merchant_id: str
    title: str
    problem: str
    evidence: list[OpportunityEvidence]
    financial_impact: FinancialImpact
    proposed_action: str
    guardrails: list[str]
    approval_required: bool = True
    status: str = "proposed"
    reasoning: str
    audit: AuditInfo


class GrowthOpportunitiesResponse(BaseModel):
    merchant_id: str
    opportunities: list[GrowthOpportunity]


class OpportunityApprovalRequest(BaseModel):
    approved: bool
    approved_by: str = Field(min_length=1)


class OpportunityApprovalResponse(BaseModel):
    opportunity_id: str
    merchant_id: str
    status: str
    approved_by: str | None = None
    approved_at: str | None = None
    proposed_action: str
    guardrails: list[str]


class ExecutionGateResponse(BaseModel):
    authorized: bool
    merchant_id: str
    opportunity_id: str
    status: str
    approved_by: str | None = None
    approved_at: str | None = None
    proposed_action: str
    guardrails: list[str]
    authorization_timestamp: str


class SimulatedExecutionRequest(BaseModel):
    discount_percent: float = Field(gt=0, le=100, description="Discount percentage (0-100)")


class SimulatedDiscountResult(BaseModel):
    discount_amount: str
    final_price: str


class SimulatedExecutionResponse(BaseModel):
    execution_id: str
    opportunity_id: str
    merchant_id: str
    action_type: str
    original_value: str
    requested_value: str
    bounded_value: str
    simulated_result: SimulatedDiscountResult
    guardrails_checked: int
    status: str
    approval_required: bool = True
    timestamp: str
    disclaimer: str


# ---------------------------------------------------------------------------
# Audit Trail schemas
# ---------------------------------------------------------------------------


class AuditEventMetadata(BaseModel):
    """Additional structured data attached to an audit event.

    This is an open dictionary — different event types carry different metadata.
    Examples:
        - opportunity_created: { proposed_action, guardrails }
        - approval_granted: { approved_by, new_status }
        - simulated_action_completed: { discount_amount, final_price, original_price }
    """

    class Config:
        extra = "allow"

    pass


class AuditEvent(BaseModel):
    """A single audit event in the decision chain."""

    event_id: str
    event_type: str
    merchant_id: str
    opportunity_id: str
    timestamp: str
    actor: Literal["system", "merchant", "agent"] = "system"
    status: str = ""
    reason: str = ""
    metadata: dict[str, Any] = {}


class AuditEventsListResponse(BaseModel):
    """Paginated list of audit events for a merchant."""

    merchant_id: str
    events: list[AuditEvent]
    total_count: int
    limit: int
    offset: int
    newest_first: bool


class AuditTrailResponse(BaseModel):
    """Complete lifecycle audit trail for a single opportunity."""

    merchant_id: str
    opportunity_id: str
    events: list[AuditEvent]
    total_events: int


class BuyerChatRequest(BaseModel):
    merchant_id: UUID
    message: str = Field(min_length=1)


class BuyerChatProduct(BaseModel):
    product_id: UUID
    name: str
    price: str
    currency: str
    similarity: float


class BuyerChatResponse(BaseModel):
    merchant_id: str
    message: str
    products: list[BuyerChatProduct]


# ---------------------------------------------------------------------------
# Checkout / Order schemas
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Request to create a pending order and Razorpay payment order."""
    merchant_id: UUID
    product_id: UUID
    quantity: int = Field(ge=1, description="Number of units (must be >= 1)")


class CheckoutResponse(BaseModel):
    """Response with order details and Razorpay order info."""
    order_id: str
    razorpay_order_id: str
    razorpay_key_id: str
    amount_paise: int
    currency: str
    product_name: str
    unit_price: str
    total_amount: str
    quantity: int
    merchant_name: str
    status: str
    environment: str = "TEST_MODE"


class PaymentVerifyRequest(BaseModel):
    """Request to verify payment after Razorpay checkout."""
    order_id: UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerifyResponse(BaseModel):
    """Response after payment verification."""
    order_id: str
    status: str
    razorpay_payment_id: str | None = None
    total_amount: str | None = None
    idempotent: bool = False


class WebhookResponse(BaseModel):
    """Response for webhook processing."""
    status: str
    order_id: str | None = None
    reason: str | None = None
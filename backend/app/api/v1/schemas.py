from datetime import datetime
from decimal import Decimal
from uuid import UUID

from typing import Literal

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
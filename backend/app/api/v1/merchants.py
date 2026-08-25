from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.growth_service import (
    RecommendationGenerationError,
    generate_recommendations,
)
from app.ai.provider import LLMError, LLMProvider, get_llm_provider
from app.api.v1.merchant_service import check_merchant_exists, create_merchant
from app.api.v1.readiness_service import analyze_readiness
from app.api.v1.schemas import (
    GrowthRecommendationsResponse,
    MerchantOnboardingRequest,
    MerchantOnboardingResponse,
    ProductCreate,
    ProductResponse,
    ReadinessResponse,
)
from app.db.session import get_db
from app.models.merchant import Merchant, MerchantStatus
from app.models.product import Product

router = APIRouter(prefix="/api/v1", tags=["merchants"])


@router.post(
    "/merchants",
    response_model=MerchantOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
)
def onboard_merchant(
    request: MerchantOnboardingRequest,
    db: Session = Depends(get_db),
) -> MerchantOnboardingResponse:
    if check_merchant_exists(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A merchant with this email already exists",
        )

    try:
        user_id, merchant_id = create_merchant(db, request)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A merchant with this email already exists",
        )

    return MerchantOnboardingResponse(
        user_id=str(user_id),
        merchant_id=str(merchant_id),
        name=request.name,
        status=MerchantStatus.ACTIVE.value,
    )


@router.get(
    "/merchants/{merchant_id}/products",
    response_model=list[ProductResponse],
)
def list_merchant_products(
    merchant_id: UUID,
    include_inactive: bool = Query(False, description="Include inactive products"),
    db: Session = Depends(get_db),
) -> list[ProductResponse]:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    query = db.query(Product).filter(Product.merchant_id == merchant_id)
    if not include_inactive:
        query = query.filter(Product.is_active.is_(True))
    products = query.order_by(Product.created_at.desc()).all()

    return [ProductResponse.model_validate(p) for p in products]


@router.post(
    "/merchants/{merchant_id}/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product_for_merchant(
    merchant_id: UUID,
    payload: ProductCreate,
    db: Session = Depends(get_db),
) -> ProductResponse:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    product = Product(
        merchant_id=merchant_id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        price=payload.price,
        currency=payload.currency,
        inventory_quantity=payload.inventory_quantity,
        delivery_info=payload.delivery_info,
        return_policy=payload.return_policy,
        is_active=True,
    )
    db.add(product)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create product",
        )

    db.refresh(product)
    return ProductResponse.model_validate(product)


@router.get(
    "/merchants/{merchant_id}/readiness",
    response_model=ReadinessResponse,
)
def get_merchant_readiness(
    merchant_id: UUID,
    db: Session = Depends(get_db),
) -> ReadinessResponse:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    products = (
        db.query(Product)
        .filter(Product.merchant_id == merchant_id)
        .filter(Product.is_active.is_(True))
        .all()
    )

    overall_score, products_analyzed, issues = analyze_readiness(products)

    return ReadinessResponse(
        merchant_id=str(merchant_id),
        overall_score=overall_score,
        products_analyzed=products_analyzed,
        issues_count=len(issues),
        issues=issues,
    )


@router.get(
    "/merchants/{merchant_id}/growth-recommendations",
    response_model=GrowthRecommendationsResponse,
)
def get_growth_recommendations(
    merchant_id: UUID,
    db: Session = Depends(get_db),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> GrowthRecommendationsResponse:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        )

    products = (
        db.query(Product)
        .filter(Product.merchant_id == merchant_id)
        .filter(Product.is_active.is_(True))
        .all()
    )

    _, _, issues = analyze_readiness(products)

    try:
        recommendations = generate_recommendations(issues, llm_provider)
    except RecommendationGenerationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an unusable response.",
        )
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI recommendation service is temporarily unavailable.",
        )

    return GrowthRecommendationsResponse(
        merchant_id=str(merchant_id),
        recommendations=recommendations,
    )

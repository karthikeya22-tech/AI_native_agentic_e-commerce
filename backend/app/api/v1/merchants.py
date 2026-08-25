from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.merchant_service import check_merchant_exists, create_merchant
from app.api.v1.schemas import MerchantOnboardingRequest, MerchantOnboardingResponse
from app.db.session import get_db
from app.models.merchant import MerchantStatus

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

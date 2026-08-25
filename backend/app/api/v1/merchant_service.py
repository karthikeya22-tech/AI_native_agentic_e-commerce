from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.schemas import MerchantOnboardingRequest
from app.models.merchant import Merchant, MerchantStatus
from app.models.user import User, UserRole


def create_merchant(
    db: Session, request: MerchantOnboardingRequest
) -> tuple[UUID, UUID]:
    """
    Create a merchant account with user and merchant records in a single transaction.
    
    Returns:
        tuple: (user_id, merchant_id)
    
    Raises:
        IntegrityError: If email already exists or merchant creation fails
    """
    try:
        # Create user with merchant role
        user = User(
            email=request.email,
            name=request.name,
            role=UserRole.MERCHANT,
        )
        db.add(user)
        db.flush()  # Flush to get user.id without committing

        # Create merchant record linked to the user
        merchant = Merchant(
            user_id=user.id,
            name=request.name,
            category=request.category,
            description=request.description,
            ai_readiness_score=None,
            status=MerchantStatus.ACTIVE,
        )
        db.add(merchant)
        db.commit()
        db.refresh(merchant)

        return user.id, merchant.id

    except IntegrityError:
        db.rollback()
        raise


def check_merchant_exists(db: Session, email: str) -> bool:
    """Check if a merchant user already exists with the given email."""
    user = (
        db.query(User)
        .filter(User.email == email, User.role == UserRole.MERCHANT)
        .first()
    )
    return user is not None
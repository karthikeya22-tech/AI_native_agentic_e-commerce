import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class MerchantPolicy(Base):
    __tablename__ = "merchant_policies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    merchant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    negotiation_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    max_discount_pct = Column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    min_allowed_price = Column(
        Numeric(12, 2),
        nullable=True,
    )

    requires_approval = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    policy_config = Column(
        JSONB,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "max_discount_pct >= 0 AND max_discount_pct <= 100",
            name="ck_policies_max_discount_pct",
        ),
        CheckConstraint(
            "min_allowed_price IS NULL OR min_allowed_price >= 0",
            name="ck_policies_min_allowed_price",
        ),
    )

    merchant = relationship(
        "Merchant",
        back_populates="policies",
    )

    product = relationship(
        "Product",
        back_populates="policies",
    )

    def __repr__(self):
        return f"<MerchantPolicy(id={self.id}, merchant_id={self.merchant_id})>"
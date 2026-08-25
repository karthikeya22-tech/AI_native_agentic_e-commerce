import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class Product(Base):
    __tablename__ = "products"

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

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)

    price = Column(
        Numeric(12, 2),
        nullable=False,
    )

    currency = Column(
        String(3),
        nullable=False,
        default="INR",
    )

    inventory_quantity = Column(
        Integer,
        nullable=False,
        default=0,
    )

    delivery_info = Column(
        JSONB,
        nullable=True,
    )

    return_policy = Column(
        Text,
        nullable=True,
    )

    product_metadata = Column(
        "metadata",
        JSONB,
        nullable=True,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
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
            "price >= 0",
            name="ck_products_price_non_negative",
        ),
        CheckConstraint(
            "inventory_quantity >= 0",
            name="ck_products_inventory_non_negative",
        ),
    )

    merchant = relationship(
        "Merchant",
        back_populates="products",
    )

    policies = relationship(
        "MerchantPolicy",
        back_populates="product",
    )

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, price={self.price})>"
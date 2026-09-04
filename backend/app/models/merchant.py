import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class MerchantStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )

    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    ai_readiness_score = Column(
        Numeric(5, 2),
        nullable=True,
    )

    status = Column(
        SQLEnum(MerchantStatus, name="merchant_status",values_callable=lambda enum_cls: [member.value for member in enum_cls],),
        nullable=False,
        default=MerchantStatus.ACTIVE,
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
            "ai_readiness_score IS NULL OR "
            "(ai_readiness_score >= 0 AND ai_readiness_score <= 100)",
            name="ck_merchants_ai_readiness_score",
        ),
    )

    user = relationship(
        "User",
        back_populates="merchant",
    )

    products = relationship(
        "Product",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )

    policies = relationship(
        "MerchantPolicy",
        back_populates="merchant",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Merchant(id={self.id}, name={self.name}, status={self.status})>"
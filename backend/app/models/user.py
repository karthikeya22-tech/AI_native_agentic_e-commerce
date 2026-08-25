import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    BUYER = "buyer"
    MERCHANT = "merchant"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)

    role = Column(
        SQLEnum(UserRole,name="user_role",values_callable=lambda enum_cls: [member.value for member in enum_cls],),
        nullable=False,
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

    merchant = relationship(
        "Merchant",
        back_populates="user",
        uselist=False,
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
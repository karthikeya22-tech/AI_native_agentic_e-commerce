#!/usr/bin/env python3
"""
Development/demo data seed script.

Creates:
- 3 fictional merchant users
- 3 merchants
- 30 electronics products
- Product-level negotiation policies
- Merchant-level default policies

The script is safe to run repeatedly:
- Existing records are reused.
- Missing products/policies are created.
- Existing records are not duplicated.

Schema creation is NOT handled here.
Alembic is the sole owner of database schema migrations.
"""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.merchant import Merchant, MerchantStatus
from app.models.policy import MerchantPolicy
from app.models.product import Product
from app.models.user import User, UserRole


MERCHANT_DATA = [
    {
        "name": "TechKart",
        "category": "Electronics Retailer",
        "description": (
            "A fictional online electronics retailer specializing in "
            "computing and consumer technology."
        ),
        "email": "techkart@demo.local",
        "ai_readiness_score": Decimal("91.00"),
    },
    {
        "name": "MobileHub",
        "category": "Mobile Devices",
        "description": (
            "A fictional retailer focused on smartphones, tablets, "
            "mobile accessories, and connected devices."
        ),
        "email": "mobilehub@demo.local",
        "ai_readiness_score": Decimal("86.00"),
    },
    {
        "name": "GadgetZone",
        "category": "Gadgets & Wearables",
        "description": (
            "A fictional store offering gadgets, wearables, audio devices, "
            "and smart home technology."
        ),
        "email": "gadgetzone@demo.local",
        "ai_readiness_score": Decimal("82.00"),
    },
]


PRODUCT_TEMPLATES = [
    {
        "base_name": "Smartphone",
        "category": "Smartphone",
        "description": (
            "A modern smartphone with a high-resolution display, "
            "fast processor, capable cameras, and all-day battery life."
        ),
        "price_range": (15000, 70000),
    },
    {
        "base_name": "Laptop",
        "category": "Laptop",
        "description": (
            "A versatile laptop designed for productivity, development, "
            "multimedia workloads, and everyday computing."
        ),
        "price_range": (35000, 120000),
    },
    {
        "base_name": "Tablet",
        "category": "Tablet",
        "description": (
            "A portable tablet with a vivid display, long battery life, "
            "and support for productivity and entertainment."
        ),
        "price_range": (20000, 65000),
    },
    {
        "base_name": "Wireless Headphones",
        "category": "Audio",
        "description": (
            "Over-ear wireless headphones featuring active noise "
            "cancellation, comfortable cushions, and long battery life."
        ),
        "price_range": (3000, 25000),
    },
    {
        "base_name": "Smartwatch",
        "category": "Wearable",
        "description": (
            "A fitness-focused smartwatch with health tracking, "
            "notifications, and activity monitoring."
        ),
        "price_range": (5000, 30000),
    },
    {
        "base_name": "Digital Camera",
        "category": "Camera",
        "description": (
            "A compact mirrorless camera designed for photography and "
            "high-resolution video capture."
        ),
        "price_range": (25000, 100000),
    },
    {
        "base_name": "Gaming Console",
        "category": "Gaming",
        "description": (
            "A modern gaming console designed for high-performance "
            "gaming and immersive entertainment."
        ),
        "price_range": (30000, 55000),
    },
    {
        "base_name": "Wi-Fi 6 Router",
        "category": "Networking",
        "description": (
            "A high-speed Wi-Fi 6 router with mesh support for reliable "
            "whole-home wireless coverage."
        ),
        "price_range": (4000, 15000),
    },
    {
        "base_name": "Drone",
        "category": "Drone",
        "description": (
            "A compact camera drone with stabilized video, intelligent "
            "flight features, and extended flight time."
        ),
        "price_range": (20000, 80000),
    },
    {
        "base_name": "Portable Bluetooth Speaker",
        "category": "Audio",
        "description": (
            "A portable Bluetooth speaker designed for rich audio, "
            "durability, and long battery life."
        ),
        "price_range": (2000, 12000),
    },
]


def get_or_create_user(
    db: Session,
    email: str,
    name: str,
) -> User:
    """Find an existing merchant user or create one."""

    user = db.query(User).filter(User.email == email).first()

    if user:
        return user

    user = User(
        id=uuid.uuid4(),
        email=email,
        name=name,
        role=UserRole.MERCHANT,
    )

    db.add(user)
    db.flush()

    return user


def get_or_create_merchant(
    db: Session,
    merchant_data: dict,
    user_id: uuid.UUID,
) -> Merchant:
    """Find an existing merchant or create one."""

    merchant = (
        db.query(Merchant)
        .filter(Merchant.name == merchant_data["name"])
        .first()
    )

    if merchant:
        return merchant

    merchant = Merchant(
        id=uuid.uuid4(),
        user_id=user_id,
        name=merchant_data["name"],
        category=merchant_data["category"],
        description=merchant_data["description"],
        ai_readiness_score=merchant_data["ai_readiness_score"],
        status=MerchantStatus.ACTIVE,
    )

    db.add(merchant)
    db.flush()

    return merchant


def get_product_price(template: dict, index: int) -> Decimal:
    """
    Generate deterministic synthetic pricing.

    Using deterministic values makes repeated development runs easier
    to reason about.
    """

    low, high = template["price_range"]

    percentage = ((index + 1) * 17) % 101
    raw_price = low + (high - low) * percentage / 100

    return Decimal(str(round(raw_price, 2)))


def get_or_create_product(
    db: Session,
    merchant: Merchant,
    template: dict,
    index: int,
) -> Product:
    """Find an existing product or create one."""

    product_name = f"{merchant.name} {template['base_name']} {index + 1}"

    product = (
        db.query(Product)
        .filter(
            Product.merchant_id == merchant.id,
            Product.name == product_name,
        )
        .first()
    )

    if product:
        return product

    price = get_product_price(template, index)

    product = Product(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        name=product_name,
        description=(
            f"{template['description']} "
            f"This is synthetic development data for {merchant.name}."
        ),
        category=template["category"],
        price=price,
        currency="INR",
        inventory_quantity=100,
        delivery_info={
            "shipping": "standard",
            "estimated_days": 3,
            "service_area": "India",
        },
        return_policy="30-day hassle-free return",
        product_metadata={
            "demo": True,
            "synthetic": True,
            "brand": merchant.name,
        },
        is_active=True,
    )

    db.add(product)
    db.flush()

    return product


def get_or_create_product_policy(
    db: Session,
    merchant: Merchant,
    product: Product,
) -> MerchantPolicy:
    """Find or create the product-specific negotiation policy."""

    policy = (
        db.query(MerchantPolicy)
        .filter(
            MerchantPolicy.merchant_id == merchant.id,
            MerchantPolicy.product_id == product.id,
        )
        .first()
    )

    if policy:
        return policy

    # 15% maximum discount means the minimum allowed price
    # must be 85% of the original price.
    min_allowed_price = (
        product.price * Decimal("0.85")
    ).quantize(Decimal("0.01"))

    policy = MerchantPolicy(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        product_id=product.id,
        negotiation_enabled=True,
        max_discount_pct=Decimal("15.00"),
        min_allowed_price=min_allowed_price,
        requires_approval=False,
        policy_config={
            "demo": True,
            "authority": "bounded",
        },
    )

    db.add(policy)
    db.flush()

    return policy


def get_or_create_default_policy(
    db: Session,
    merchant: Merchant,
) -> MerchantPolicy:
    """Find or create a merchant-wide default policy."""

    policy = (
        db.query(MerchantPolicy)
        .filter(
            MerchantPolicy.merchant_id == merchant.id,
            MerchantPolicy.product_id.is_(None),
        )
        .first()
    )

    if policy:
        return policy

    policy = MerchantPolicy(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        product_id=None,
        negotiation_enabled=True,
        max_discount_pct=Decimal("10.00"),
        min_allowed_price=None,
        requires_approval=True,
        policy_config={
            "default": True,
            "demo": True,
        },
    )

    db.add(policy)
    db.flush()

    return policy


def seed_merchant(
    db: Session,
    merchant_data: dict,
) -> None:
    """Seed one merchant and all associated development data."""

    user = get_or_create_user(
        db=db,
        email=merchant_data["email"],
        name=merchant_data["name"],
    )

    merchant = get_or_create_merchant(
        db=db,
        merchant_data=merchant_data,
        user_id=user.id,
    )

    get_or_create_default_policy(
        db=db,
        merchant=merchant,
    )

    for index, template in enumerate(PRODUCT_TEMPLATES):
        product = get_or_create_product(
            db=db,
            merchant=merchant,
            template=template,
            index=index,
        )

        get_or_create_product_policy(
            db=db,
            merchant=merchant,
            product=product,
        )


def main() -> None:
    """
    Seed development data.

    IMPORTANT:
    This script does not create or modify database schema.
    Alembic is responsible for schema migrations.
    """

    db = SessionLocal()

    try:
        for merchant_data in MERCHANT_DATA:
            seed_merchant(
                db=db,
                merchant_data=merchant_data,
            )

        db.commit()

        print("Demo data seeded successfully.")
        print("Merchants: 3")
        print("Products: 30")
        print("Merchant/product policies: seeded")
        print("Merchant default policies: seeded")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
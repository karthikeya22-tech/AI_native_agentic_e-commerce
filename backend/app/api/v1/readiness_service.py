"""Deterministic commerce-readiness scoring engine.

No LLM calls: the score is computed purely from product fields so the same
database state always produces the same score and issues.
"""

from typing import Any, Iterable, Sequence

# Weights out of 100 per active product.
DESCRIPTION_WEIGHT = 25
CATEGORY_WEIGHT = 10
PRICE_WEIGHT = 20
INVENTORY_WEIGHT = 10
DELIVERY_INFO_WEIGHT = 10
RETURN_POLICY_WEIGHT = 10
METADATA_WEIGHT = 15

# A description shorter than this many characters counts as "very short".
DESCRIPTION_MIN_LENGTH = 40


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _issue(
    product_id,
    product_name: str,
    issue_type: str,
    description: str,
    severity: str,
    suggested_action: str,
) -> dict:
    return {
        "product_id": str(product_id),
        "product_name": product_name,
        "issue_type": issue_type,
        "description": description,
        "severity": severity,
        "suggested_action": suggested_action,
    }


def evaluate_product(product: Any) -> tuple[int, list[dict]]:
    """Score a single active product out of 100 and collect its issues."""
    score = 100
    issues: list[dict] = []
    name = product.name or ""

    # 1. Description quality (25): missing = 0, very short = partial, else full.
    description = product.description or ""
    if not _has_text(description):
        score -= DESCRIPTION_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "missing_description",
                "Product has no description.",
                "high",
                "Add a descriptive summary of at least "
                f"{DESCRIPTION_MIN_LENGTH} characters.",
            )
        )
    elif len(description.strip()) < DESCRIPTION_MIN_LENGTH:
        score -= DESCRIPTION_WEIGHT // 2
        issues.append(
            _issue(
                product.id,
                name,
                "short_description",
                "Product description is too short to be useful.",
                "medium",
                f"Expand the description to at least {DESCRIPTION_MIN_LENGTH} characters.",
            )
        )

    # 2. Category completeness (10).
    if not _has_text(product.category):
        score -= CATEGORY_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "missing_category",
                "Product has no category.",
                "medium",
                "Assign a category so AI buyers can discover the product.",
            )
        )

    # 3. Valid price (20): must be greater than zero.
    price = product.price
    if price is None or price <= 0:
        score -= PRICE_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "invalid_price",
                "Product price is missing or not greater than zero.",
                "high",
                "Set a positive selling price.",
            )
        )

    # 4. Inventory information (10): field present and non-negative.
    inventory = product.inventory_quantity
    if inventory is None or inventory < 0:
        score -= INVENTORY_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "invalid_inventory",
                "Inventory quantity is missing or negative.",
                "low",
                "Set a non-negative stock quantity.",
            )
        )

    # 5. Delivery information (10).
    if not _is_non_empty(product.delivery_info):
        score -= DELIVERY_INFO_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "missing_delivery_info",
                "Delivery information is missing or empty.",
                "medium",
                "Add delivery details such as estimated delivery days.",
            )
        )

    # 6. Return policy (10).
    if not _has_text(product.return_policy):
        score -= RETURN_POLICY_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "missing_return_policy",
                "Return policy is missing or empty.",
                "medium",
                "State a clear return policy.",
            )
        )

    # 7. Structured metadata/specifications (15).
    if not _is_non_empty(product.product_metadata):
        score -= METADATA_WEIGHT
        issues.append(
            _issue(
                product.id,
                name,
                "missing_metadata",
                "Structured specifications/metadata are missing.",
                "low",
                "Add structured specs (brand, dimensions, etc.) to improve "
                "AI discoverability.",
            )
        )

    return max(score, 0), issues


def analyze_readiness(products: Sequence[Any]) -> tuple[int, int, list[dict]]:
    """Analyze active products.

    Returns:
        tuple: (overall_score, products_analyzed, issues)

    The overall score is the mean per-product score across all analyzed
    products, rounded to the nearest integer. With no products it is 0.
    """
    issues: list[dict] = []

    if not products:
        return 0, 0, issues

    total = 0
    for product in products:
        product_score, product_issues = evaluate_product(product)
        total += product_score
        issues.extend(product_issues)

    overall = round(total / len(products))
    return overall, len(products), issues

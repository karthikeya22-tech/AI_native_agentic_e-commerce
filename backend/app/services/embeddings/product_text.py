"""
Canonical product-to-text formatting for embeddings.

This module is the SINGLE place where a Product is converted into the
semantic text that gets embedded. It intentionally includes only
descriptive/product content:

- name
- category
- description
- delivery information (structured JSONB)
- return policy
- structured metadata/specifications (JSONB)

It deliberately EXCLUDES business-rule data:
- inventory quantity (stock levels are not semantic content)
- price / currency / merchant policies / negotiation rules

Financial and business constraints must never influence vector
similarity; they remain enforced by deterministic checks.
"""

from typing import Any


def _format_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).strip()


def _format_json_fields(data: Any) -> list[str]:
    """Flatten a JSONB object into 'key: value' lines."""
    if not isinstance(data, dict):
        return []
    parts: list[str] = []
    for key, value in data.items():
        label = str(key).replace("_", " ").strip()
        if isinstance(value, dict):
            nested = _format_json_fields(value)
            parts.extend(f"{label} {part}" for part in nested)
        elif isinstance(value, list):
            rendered = ", ".join(_format_scalar(item) for item in value if _format_scalar(item))
            if rendered:
                parts.append(f"{label}: {rendered}")
        else:
            rendered = _format_scalar(value)
            if rendered:
                parts.append(f"{label}: {rendered}")
    return parts


def build_product_embedding_text(product) -> str:
    """
    Build the canonical text representation of a product for embedding.

    Safe to call with any Product-like object exposing the standard
    product columns.
    """
    sections: list[str] = []

    name = _format_scalar(getattr(product, "name", None))
    if name:
        sections.append(name)

    category = _format_scalar(getattr(product, "category", None))
    if category:
        sections.append(f"Category: {category}")

    description = _format_scalar(getattr(product, "description", None))
    if description:
        sections.append(description)

    delivery_lines = _format_json_fields(getattr(product, "delivery_info", None))
    if delivery_lines:
        sections.append("Delivery: " + "; ".join(delivery_lines))

    return_policy = _format_scalar(getattr(product, "return_policy", None))
    if return_policy:
        sections.append(f"Return policy: {return_policy}")

    metadata_lines = _format_json_fields(
        getattr(product, "product_metadata", None)
        or getattr(product, "metadata", None)
    )
    if metadata_lines:
        sections.append("Specifications: " + "; ".join(metadata_lines))

    return "\n".join(section for section in sections if section.strip())

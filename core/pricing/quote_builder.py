from core.pricing.config import (
    COMPLEXITY_MULTIPLIERS,
    DESIGN_MULTIPLIERS,
    URGENCY_MULTIPLIERS,
)
from core.pricing.selector import select_components


def _get_multiplier_range(normalized_spec: dict) -> tuple[float, float]:
    complexity = normalized_spec.get("complexity", "unknown")
    design_level = normalized_spec.get("design_level", "unknown")
    urgency = normalized_spec.get("urgency", "unknown")

    complexity_min, complexity_max = COMPLEXITY_MULTIPLIERS.get(
        complexity, COMPLEXITY_MULTIPLIERS["unknown"]
    )
    design_min, design_max = DESIGN_MULTIPLIERS.get(
        design_level, DESIGN_MULTIPLIERS["unknown"]
    )
    urgency_min, urgency_max = URGENCY_MULTIPLIERS.get(
        urgency, URGENCY_MULTIPLIERS["unknown"]
    )

    return (
        complexity_min * design_min * urgency_min,
        complexity_max * design_max * urgency_max,
    )


def _adjust_component_price(component: dict, min_multiplier: float, max_multiplier: float) -> dict:
    base_min = component["price_min"]
    base_max = component["price_max"]

    adjusted_min = int(base_min * min_multiplier)
    adjusted_max = int(base_max * max_multiplier)

    return {
        **component,
        "base_price_min": base_min,
        "base_price_max": base_max,
        "price_min": adjusted_min,
        "price_max": adjusted_max,
    }


def _group_items(items: list[dict]) -> dict:
    grouped = {
        "core": [],
        "integration": [],
        "optional": [],
        "delivery": [],
        "recurring": [],
    }

    for item in items:
        category = item.get("category", "optional")
        if category not in grouped:
            grouped[category] = []
        grouped[category].append(item)

    return grouped


def build_quote(normalized_spec: dict) -> dict:
    components = select_components(normalized_spec)
    min_multiplier, max_multiplier = _get_multiplier_range(normalized_spec)

    adjusted_items = [
        _adjust_component_price(component, min_multiplier, max_multiplier)
        for component in components
    ]

    grouped_items = _group_items(adjusted_items)

    one_time_items = [item for item in adjusted_items if not item.get("recurring", False)]
    recurring_items = [item for item in adjusted_items if item.get("recurring", False)]

    subtotal_min = sum(item["price_min"] for item in one_time_items)
    subtotal_max = sum(item["price_max"] for item in one_time_items)

    recurring_min = sum(item["price_min"] for item in recurring_items)
    recurring_max = sum(item["price_max"] for item in recurring_items)

    return {
        "project_type": normalized_spec.get("project_type", "unknown"),
        "business_goal": normalized_spec.get("business_goal", ""),
        "currency": "MAD",
        "groups": grouped_items,
        "items": adjusted_items,
        "subtotal_min": subtotal_min,
        "subtotal_max": subtotal_max,
        "recurring_min": recurring_min,
        "recurring_max": recurring_max,
        "notes": [
            "Final pricing depends on confirmed scope and technical requirements.",
            "Third-party service fees are not included unless explicitly stated.",
            "Recurring costs such as hosting or API usage may vary depending on usage volume.",
        ],
        "missing_information": normalized_spec.get("missing_information", []),
        "confidence": normalized_spec.get("confidence", 0.0),
    }
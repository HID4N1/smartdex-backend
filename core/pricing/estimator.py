from core.pricing.config import (
    BASE_PRICE_RANGES,
    FEATURE_MODIFIERS,
    INTEGRATION_MODIFIERS,
    COMPLEXITY_MULTIPLIERS,
    DESIGN_MULTIPLIERS,
    URGENCY_MULTIPLIERS,
    QUALIFICATION_THRESHOLDS,
)


def _apply_percentage_modifiers(
    base_min: int,
    base_max: int,
    features: list[str],
    integrations: list[str],
) -> tuple[float, float]:
    min_total = float(base_min)
    max_total = float(base_max)

    for feature in features:
        min_pct, max_pct = FEATURE_MODIFIERS.get(feature, (0.03, 0.08))
        min_total += base_min * min_pct
        max_total += base_max * max_pct

    for integration in integrations:
        min_pct, max_pct = INTEGRATION_MODIFIERS.get(integration, (0.03, 0.08))
        min_total += base_min * min_pct
        max_total += base_max * max_pct

    return min_total, max_total


def _classify_project(estimated_max: int) -> tuple[str, str]:
    if estimated_max <= QUALIFICATION_THRESHOLDS["small_project_max"]:
        return (
            "small_project",
            "This looks suitable for a focused MVP or smaller business project.",
        )

    if estimated_max <= QUALIFICATION_THRESHOLDS["mid_project_max"]:
        return (
            "mid_project",
            "This looks like a medium-scope project. A phased delivery or MVP-first approach is recommended.",
        )

    return (
        "large_project",
        "This appears to be a high-scope project. A requirement workshop is recommended before a final quote.",
    )


def estimate_project(normalized_spec: dict) -> dict:
    project_type = normalized_spec.get("project_type", "unknown")
    features = normalized_spec.get("features", [])
    integrations = normalized_spec.get("integrations", [])
    complexity = normalized_spec.get("complexity", "unknown")
    design_level = normalized_spec.get("design_level", "unknown")
    urgency = normalized_spec.get("urgency", "unknown")
    confidence = normalized_spec.get("confidence", 0.0)
    missing_information = normalized_spec.get("missing_information", [])

    base_min, base_max = BASE_PRICE_RANGES.get(project_type, BASE_PRICE_RANGES["unknown"])

    adjusted_min, adjusted_max = _apply_percentage_modifiers(
        base_min=base_min,
        base_max=base_max,
        features=features,
        integrations=integrations,
    )

    complexity_min_mult, complexity_max_mult = COMPLEXITY_MULTIPLIERS.get(
        complexity, COMPLEXITY_MULTIPLIERS["unknown"]
    )
    design_min_mult, design_max_mult = DESIGN_MULTIPLIERS.get(
        design_level, DESIGN_MULTIPLIERS["unknown"]
    )
    urgency_min_mult, urgency_max_mult = URGENCY_MULTIPLIERS.get(
        urgency, URGENCY_MULTIPLIERS["unknown"]
    )

    estimated_min = int(adjusted_min * complexity_min_mult * design_min_mult * urgency_min_mult)
    estimated_max = int(adjusted_max * complexity_max_mult * design_max_mult * urgency_max_mult)

    cost_drivers = []

    if project_type != "unknown":
        cost_drivers.append(f"Project type: {project_type}")

    if features:
        cost_drivers.append(f"Features: {', '.join(features)}")

    if integrations:
        cost_drivers.append(f"Integrations: {', '.join(integrations)}")

    if complexity != "unknown":
        cost_drivers.append(f"Complexity: {complexity}")

    if design_level != "unknown":
        cost_drivers.append(f"Design level: {design_level}")

    if urgency != "unknown":
        cost_drivers.append(f"Urgency: {urgency}")

    qualification, recommendation = _classify_project(estimated_max)

    return {
        "project_type": project_type,
        "estimated_range_min": estimated_min,
        "estimated_range_max": estimated_max,
        "currency": "MAD",
        "qualification": qualification,
        "cost_drivers": cost_drivers,
        "recommendation": recommendation,
        "confidence": confidence,
        "missing_information": missing_information,
    }
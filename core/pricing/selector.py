from core.pricing.catalog import QUOTE_CATALOG


def select_components(normalized_spec: dict) -> list[dict]:
    project_type = normalized_spec.get("project_type")
    features = normalized_spec.get("features", [])
    integrations = normalized_spec.get("integrations", [])

    selected_keys = set()

    # 1. Add required components based on project type
    for key, item in QUOTE_CATALOG.items():
        if project_type in item.get("required_by", []):
            selected_keys.add(key)

    # 2. Add components based on features
    for feature in features:
        if feature in QUOTE_CATALOG:
            selected_keys.add(feature)

    # 3. Add components based on integrations
    for integration in integrations:
        if integration in QUOTE_CATALOG:
            selected_keys.add(integration)

    # 4. Always include deployment
    if "deployment" in QUOTE_CATALOG:
        selected_keys.add("deployment")

    # 5. Build final component list
    components = []

    for key in selected_keys:
        item = QUOTE_CATALOG[key]

        components.append({
            "key": key,
            "label": item["label"],
            "description": item["description"],
            "category": item["category"],
            "price_min": item["price_range"][0],
            "price_max": item["price_range"][1],
            "optional": item["optional"],
            "recurring": item["recurring"],
        })

    return components
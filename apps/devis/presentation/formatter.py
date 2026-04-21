# apps/devis/presentation/formatter.py

def format_generated_quote(devis_request, pipeline_result: dict) -> dict:
    estimate = pipeline_result.get("estimate", {}) or {}
    quote = pipeline_result.get("quote", {}) or {}

    groups = quote.get("groups", {}) or {}
    items = quote.get("items", []) or []

    included_groups = []
    optional_items = []
    recurring_items = []

    for group_key, group_items in groups.items():
        clean_items = []

        for item in group_items:
            formatted_item = {
                "key": item.get("key"),
                "label": item.get("label"),
                "description": item.get("description"),
                "category": item.get("category"),
                "price_min": item.get("price_min", 0),
                "price_max": item.get("price_max", 0),
            }

            if item.get("recurring"):
                recurring_items.append(formatted_item)
            elif item.get("optional"):
                optional_items.append(formatted_item)
            else:
                clean_items.append(formatted_item)

        if clean_items:
            included_groups.append({
                "key": group_key,
                "label": group_key.replace("_", " ").title(),
                "items": clean_items,
            })

    included_total_min = sum(
        item.get("price_min", 0)
        for item in items
        if not item.get("optional") and not item.get("recurring")
    )
    included_total_max = sum(
        item.get("price_max", 0)
        for item in items
        if not item.get("optional") and not item.get("recurring")
    )

    optional_total_min = sum(
        item.get("price_min", 0)
        for item in items
        if item.get("optional") and not item.get("recurring")
    )
    optional_total_max = sum(
        item.get("price_max", 0)
        for item in items
        if item.get("optional") and not item.get("recurring")
    )

    recurring_total_min = sum(
        item.get("price_min", 0)
        for item in items
        if item.get("recurring")
    )
    recurring_total_max = sum(
        item.get("price_max", 0)
        for item in items
        if item.get("recurring")
    )

    return {
        "request": {
            "id": devis_request.id,
            "status": devis_request.status,
            "created_at": devis_request.created_at,
            "client": {
                "name": devis_request.client_name,
                "email": devis_request.client_email,
                "phone": devis_request.client_phone,
            },
        },
        "summary": {
            "project_type": quote.get("project_type"),
            "business_goal": quote.get("business_goal"),
            "currency": quote.get("currency", "MAD"),
            "confidence": quote.get("confidence", estimate.get("confidence")),
            "qualification": estimate.get("qualification"),
        },
        "estimate": {
            "range_min": estimate.get("estimated_range_min"),
            "range_max": estimate.get("estimated_range_max"),
            "currency": estimate.get("currency", quote.get("currency", "MAD")),
            "cost_drivers": estimate.get("cost_drivers", []),
            "recommendation": estimate.get("recommendation"),
        },
        "quote": {
            "included_groups": included_groups,
            "optional_items": optional_items,
            "recurring_items": recurring_items,
            "totals": {
                "included_min": included_total_min,
                "included_max": included_total_max,
                "optional_min": optional_total_min,
                "optional_max": optional_total_max,
                "recurring_min": recurring_total_min,
                "recurring_max": recurring_total_max,
                "grand_total_min": included_total_min + optional_total_min,
                "grand_total_max": included_total_max + optional_total_max,
            },
            "notes": quote.get("notes", []),
            "missing_information": quote.get("missing_information", []),
        },
    }
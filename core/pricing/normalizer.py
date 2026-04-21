from core.pricing.extractor_schema import ExtractedProjectSpec


FEATURE_MAP = {
    "booking": "booking",
    "appointments": "booking",
    "reservation": "booking",
    "reservations": "booking",
    "scheduling": "booking",

    "payments": "payments",
    "payment": "payments",
    "online payments": "payments",
    "payment gateway": "payments",
    "checkout": "payments",

    "dashboard": "admin_dashboard",
    "admin dashboard": "admin_dashboard",
    "admin panel": "admin_dashboard",
    "back office": "admin_dashboard",

    "notifications": "notifications",
    "reminders": "notifications",
    "alerts": "notifications",
    "email notifications": "notifications",
    "sms notifications": "notifications",
    "whatsapp reminders": "notifications",
    "whatsapp notifications": "notifications",

    "authentication": "authentication",
    "login": "authentication",
    "sign in": "authentication",
    "sign up": "authentication",
    "user accounts": "authentication",

    "crm": "crm",
    "customer management": "crm",
    "client management": "crm",

    "analytics": "analytics",
    "reports": "analytics",
    "reporting": "analytics",
    "kpis": "analytics",
    "dashboard analytics": "analytics",

    "chatbot": "chatbot",
    "ai assistant": "chatbot",
    "support bot": "chatbot",

    "marketplace": "marketplace",
    "multi vendor": "marketplace",
    "vendors": "marketplace",

    "content management": "cms",
    "cms": "cms",
    "blog management": "cms",
}

INTEGRATION_MAP = {
    "whatsapp": "whatsapp",
    "stripe": "stripe",
    "paypal": "paypal",
    "google maps": "google_maps",
    "calendar": "calendar",
    "email": "email",
    "sms": "sms",
    "api": "external_api",
    "payment gateway": "payment_gateway",
}


PROJECT_TYPE_MAP = {
    "website": "website",
    "webapp": "webapp",
    "saas": "saas",
    "mobile_app": "mobile_app",
    "ecommerce": "ecommerce",
    "content_management_system": "content_management_system",
    "ai_system": "ai_system",
    "automation": "automation",
    "dashboard": "dashboard",
    "data_visualization": "data_visualization",
    "api_integration": "api_integration",
    "crm": "crm",
    "erp": "erp",
    "social_network": "social_network",
    "marketplace": "marketplace",
    "blog": "blog",
    "portfolio": "portfolio",
    "forum": "forum",
    "learning_management_system": "learning_management_system",
    "event_management_system": "event_management_system",
    "healthcare_system": "healthcare_system",
    "finance_system": "finance_system",
    "real_estate_system": "real_estate_system",
    "booking_system": "booking_system",
    "unknown": "unknown",
}


def _normalize_list(items: list[str], mapping: dict[str, str]) -> list[str]:
    normalized = []

    for item in items:
        key = item.strip().lower()
        normalized_value = mapping.get(key, key.replace(" ", "_"))
        if normalized_value not in normalized:
            normalized.append(normalized_value)

    return normalized


def normalize_project_spec(spec: ExtractedProjectSpec) -> dict:
    features = _normalize_list(spec.features, FEATURE_MAP)
    integrations = _normalize_list(spec.integrations, INTEGRATION_MAP)
    project_type = PROJECT_TYPE_MAP.get(spec.project_type, "unknown")

    if spec.admin_dashboard_needed and "admin_dashboard" not in features:
        features.append("admin_dashboard")

    if spec.user_accounts_needed and "authentication" not in features:
        features.append("authentication")

    if spec.payment_needed and "payments" not in features:
        features.append("payments")

    if spec.notifications_needed and "notifications" not in features:
        features.append("notifications")

    return {
        "project_type": project_type,
        "business_goal": spec.business_goal.strip(),
        "features": features,
        "integrations": integrations,
        "complexity": spec.complexity,
        "design_level": spec.design_level,
        "urgency": spec.urgency,
        "confidence": spec.confidence,
        "missing_information": spec.missing_information,
    }
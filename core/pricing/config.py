BASE_PRICE_RANGES = {
    "website": (5000, 20000),
    "webapp": (15000, 60000),
    "saas": (60000, 150000),
    "mobile_app": (40000, 120000),
    "ecommerce": (20000, 80000),
    "content_management_system": (10000, 40000),
    "ai_system": (20000, 100000),
    "automation": (8000, 40000),
    "dashboard": (10000, 30000),
    "data_visualization": (12000, 35000),
    "api_integration": (8000, 25000),
    "crm": (30000, 100000),
    "erp": (80000, 250000),
    "social_network": (60000, 180000),
    "marketplace": (70000, 200000),
    "blog": (5000, 15000),
    "portfolio": (4000, 12000),
    "forum": (15000, 50000),
    "learning_management_system": (40000, 120000),
    "event_management_system": (20000, 70000),
    "healthcare_system": (40000, 140000),
    "finance_system": (50000, 180000),
    "real_estate_system": (25000, 90000),
    "booking_system": (15000, 50000),
    "unknown": (10000, 50000),
}

FEATURE_MODIFIERS = {
    "booking": (0.10, 0.18),
    "payments": (0.10, 0.20),
    "admin_dashboard": (0.10, 0.15),
    "notifications": (0.05, 0.10),
    "authentication": (0.08, 0.12),
    "crm": (0.12, 0.20),
    "analytics": (0.10, 0.18),
    "chatbot": (0.12, 0.25),
    "marketplace": (0.18, 0.30),
    "cms": (0.08, 0.15),
}

INTEGRATION_MODIFIERS = {
    "whatsapp": (0.05, 0.10),
    "stripe": (0.08, 0.12),
    "paypal": (0.08, 0.12),
    "google_maps": (0.04, 0.08),
    "calendar": (0.03, 0.06),
    "email": (0.02, 0.05),
    "sms": (0.04, 0.08),
    "external_api": (0.08, 0.15),
    "payment_gateway": (0.08, 0.12),
}

COMPLEXITY_MULTIPLIERS = {
    "low": (1.0, 1.0),
    "medium": (1.15, 1.25),
    "high": (1.30, 1.60),
    "unknown": (1.05, 1.15),
}

DESIGN_MULTIPLIERS = {
    "basic": (1.0, 1.0),
    "standard": (1.05, 1.10),
    "premium": (1.12, 1.25),
    "unknown": (1.0, 1.05),
}

URGENCY_MULTIPLIERS = {
    "normal": (1.0, 1.0),
    "urgent": (1.10, 1.20),
    "unknown": (1.0, 1.05),
}

QUALIFICATION_THRESHOLDS = {
    "small_project_max": 30000,
    "mid_project_max": 100000,
}
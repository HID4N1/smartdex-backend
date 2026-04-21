from typing import List, Literal, Optional
from pydantic import BaseModel, Field


ProjectType = Literal[
    "website",
    "webapp",
    "saas",
    "mobile_app",
    "ecommerce",
    "content_management_system",
    "ai_system",
    "automation",
    "dashboard",
    "data_visualization",
    "api_integration",
    "crm",
    "erp",
    "social_network",
    "marketplace",
    "blog",
    "portfolio",
    "forum",
    "learning_management_system",
    "event_management_system",
    "healthcare_system",
    "finance_system",
    "real_estate_system",
    "booking_system",
    "unknown",
]

ComplexityLevel = Literal["low", "medium", "high", "unknown"]
DesignLevel = Literal["basic", "standard", "premium", "unknown"]
UrgencyLevel = Literal["normal", "urgent", "unknown"]


class ExtractedProjectSpec(BaseModel):
    project_type: ProjectType = Field(
        description="Best-fit project category based on the user's request."
    )
    business_goal: str = Field(
        description="Short plain-language summary of what the user wants to achieve."
    )
    features: List[str] = Field(
        default_factory=list,
        description="Normalized business features requested by the user."
    )
    integrations: List[str] = Field(
        default_factory=list,
        description="External integrations explicitly or strongly implicitly requested."
    )
    complexity: ComplexityLevel = Field(
        description="Estimated implementation complexity."
    )
    design_level: DesignLevel = Field(
        description="Expected design quality level if mentioned or inferable."
    )
    urgency: UrgencyLevel = Field(
        description="Delivery urgency if mentioned or inferable."
    )
    admin_dashboard_needed: bool = Field(
        description="Whether the user likely needs an admin dashboard."
    )
    user_accounts_needed: bool = Field(
        description="Whether end-user accounts/authentication are likely needed."
    )
    payment_needed: bool = Field(
        description="Whether online payments are needed."
    )
    notifications_needed: bool = Field(
        description="Whether reminders, alerts, email, SMS, or WhatsApp notifications are needed."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the extraction."
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Important missing details needed for a better estimate."
    )
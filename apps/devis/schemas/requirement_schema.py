from __future__ import annotations

from pydantic import BaseModel, Field


class RequirementExtraction(BaseModel):
    project_type: str | None = None
    detected_features: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    timeline: str | None = None
    client_name: str | None = None
    client_email: str | None = None
    client_phone: str | None = None
    preferred_language: str | None = None
    complexity_hint: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)

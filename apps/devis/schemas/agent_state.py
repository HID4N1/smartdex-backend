from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ClientInfo(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    business_name: str | None = None


class InputState(BaseModel):
    user_message: str = ""
    client_info: ClientInfo = Field(default_factory=ClientInfo)


class RequirementState(BaseModel):
    project_type: str | None = None
    features_requested: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    budget_range: str | None = None
    timeline: str | None = None
    preferred_language: str | None = None
    clarity_score: float = 0.0
    raw_extraction: dict[str, Any] = Field(default_factory=dict)


class ValidationState(BaseModel):
    is_valid: bool = False
    needs_clarification: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PlanningState(BaseModel):
    selected_features: list[str] = Field(default_factory=list)
    feature_groups: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    complexity_level: str = "unknown"
    assumptions: list[str] = Field(default_factory=list)
    excluded_features: list[str] = Field(default_factory=list)


class PricingState(BaseModel):
    range_min: int = 0
    range_max: int = 0
    currency: str = "MAD"
    breakdown: dict[str, Any] = Field(default_factory=dict)
    cost_drivers: list[str] = Field(default_factory=list)
    recommendation: str = ""


class QuoteState(BaseModel):
    title: str = ""
    summary: str = ""
    included_groups: list[dict[str, Any]] = Field(default_factory=list)
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    recommendation: str = ""
    commercial_notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class PDFState(BaseModel):
    generated: bool = False
    path: str | None = None
    url: str | None = None


class MetadataState(BaseModel):
    status: Literal["pending", "needs_clarification", "processed", "failed"] = "pending"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    input: InputState = Field(default_factory=InputState)
    requirement: RequirementState = Field(default_factory=RequirementState)
    validation: ValidationState = Field(default_factory=ValidationState)
    planning: PlanningState = Field(default_factory=PlanningState)
    pricing: PricingState = Field(default_factory=PricingState)
    quote: QuoteState = Field(default_factory=QuoteState)
    pdf: PDFState = Field(default_factory=PDFState)
    metadata: MetadataState = Field(default_factory=MetadataState)

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanningResult(BaseModel):
    selected_features: list[str] = Field(default_factory=list)
    grouped_features: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    complexity_level: str = "unknown"
    assumptions: list[str] = Field(default_factory=list)
    excluded_features: list[str] = Field(default_factory=list)

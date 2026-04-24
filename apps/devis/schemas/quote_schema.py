from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuoteLineItem(BaseModel):
    key: str | None = None
    label: str = ""
    description: str = ""
    category: str = ""
    price_min: int = 0
    price_max: int = 0


class QuoteTotals(BaseModel):
    included_min: int = 0
    included_max: int = 0
    optional_min: int = 0
    optional_max: int = 0
    recurring_min: int = 0
    recurring_max: int = 0
    grand_total_min: int = 0
    grand_total_max: int = 0


class QuoteResult(BaseModel):
    included_groups: list[dict[str, Any]] = Field(default_factory=list)
    line_items: list[QuoteLineItem] = Field(default_factory=list)
    totals: QuoteTotals = Field(default_factory=QuoteTotals)
    recommendation: str = ""
    commercial_notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)

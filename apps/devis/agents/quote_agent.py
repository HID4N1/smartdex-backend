from __future__ import annotations

from apps.devis.prompts.quote_prompt import build_quote_prompt
from apps.devis.schemas.agent_state import AgentState
from apps.devis.services.llm_service import LLMService


class QuoteAgent:
    def __init__(self, llm_service: LLMService | None = None):
        self.llm_service = llm_service or LLMService()

    def run(self, state: AgentState, formatted_payload: dict) -> AgentState:
        estimate = formatted_payload.get("estimate", {})
        quote = formatted_payload.get("quote", {})
        fallback = self._fallback_quote_text(state, quote, estimate)
        prompt = build_quote_prompt(
            project_type=state.requirement.project_type or "unknown",
            included_groups=quote.get("included_groups", []),
            totals=quote.get("totals", {}),
            recommendation=estimate.get("recommendation", ""),
            preferred_language=state.requirement.preferred_language,
        )
        generated = self.llm_service.generate_quote_text(prompt=prompt, fallback=fallback)

        state.quote.title = generated.get("title", "")
        state.quote.summary = generated.get("summary", "")
        state.quote.included_groups = quote.get("included_groups", [])
        state.quote.line_items = quote.get("optional_items", []) + quote.get("recurring_items", [])
        state.quote.totals = quote.get("totals", {})
        state.quote.recommendation = generated.get("recommendation") or estimate.get("recommendation", "")
        state.quote.commercial_notes = generated.get("commercial_notes") or quote.get("notes", [])
        state.quote.next_steps = generated.get("next_steps", [])
        return state

    def _fallback_quote_text(self, state: AgentState, quote: dict, estimate: dict) -> dict:
        project_type = (state.requirement.project_type or "project").replace("_", " ")
        return {
            "title": f"SmartDex proposal for your {project_type}",
            "summary": (
                f"This proposal covers the main scope currently identified for your {project_type} "
                f"with the exact pricing range calculated by our deterministic pricing engine."
            ),
            "recommendation": estimate.get("recommendation", ""),
            "commercial_notes": quote.get("notes", []),
            "next_steps": [
                "Confirm the functional scope and priority features.",
                "Validate timeline, integrations, and delivery assumptions.",
                "Move to a final commercial proposal once scope is confirmed.",
            ],
        }

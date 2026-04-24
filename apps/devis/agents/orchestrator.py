from __future__ import annotations

import logging
from pathlib import Path
import tempfile

from django.urls import reverse

from apps.devis.agents.planning_agent import PlanningAgent
from apps.devis.agents.quote_agent import QuoteAgent
from apps.devis.agents.requirement_agent import RequirementAgent
from apps.devis.agents.validation_agent import ValidationAgent
from apps.devis.presentation.formatter import format_generated_quote
from apps.devis.schemas.agent_state import AgentState, ClientInfo, InputState
from apps.devis.services.pdf_context_builder import PDFContextBuilder
from apps.devis.services.pdf_generator import DevisPDFGenerator
from core.pricing.service import DevisService as CorePricingService

logger = logging.getLogger(__name__)


class DevisOrchestrator:
    def __init__(self):
        self.requirement_agent = RequirementAgent()
        self.validation_agent = ValidationAgent()
        self.planning_agent = PlanningAgent()
        self.quote_agent = QuoteAgent()
        self.pricing_service = CorePricingService()

    def run(self, devis_request) -> tuple[AgentState, dict]:
        state = AgentState(
            input=InputState(
                user_message=devis_request.description or "",
                client_info=ClientInfo(
                    name=devis_request.client_name or None,
                    email=devis_request.client_email or None,
                    phone=devis_request.client_phone or None,
                    business_name=getattr(devis_request, "business_name", None) or None,
                ),
            )
        )

        try:
            state = self.requirement_agent.run(state)
            state = self.validation_agent.run(state)

            if state.validation.needs_clarification:
                state.metadata.status = "needs_clarification"
                return state, self._build_clarification_payload(devis_request, state)

            state, normalized_spec = self.planning_agent.run(state)
            pipeline_result = self.pricing_service.generate_from_normalized_spec(
                normalized_spec=normalized_spec,
                description=devis_request.description,
                project_type_hint=state.requirement.project_type,
                selected_features=state.planning.selected_features,
                budget_hint=state.requirement.budget_range,
                deadline_hint=state.requirement.timeline,
                extracted_spec=state.requirement.raw_extraction,
            )
            formatted_payload = format_generated_quote(devis_request, pipeline_result)

            state.pricing.range_min = formatted_payload.get("estimate", {}).get("range_min") or 0
            state.pricing.range_max = formatted_payload.get("estimate", {}).get("range_max") or 0
            state.pricing.currency = formatted_payload.get("estimate", {}).get("currency") or "MAD"
            state.pricing.breakdown = formatted_payload.get("quote", {}).get("totals", {})
            state.pricing.cost_drivers = formatted_payload.get("estimate", {}).get("cost_drivers", [])
            state.pricing.recommendation = formatted_payload.get("estimate", {}).get("recommendation", "")

            state = self.quote_agent.run(state, formatted_payload)

            try:
                pdf_context = PDFContextBuilder.build(devis_request, formatted_payload)
                temp_dir = Path(tempfile.gettempdir())
                pdf_path = temp_dir / f"devis_{devis_request.id}.pdf"
                generated_path = DevisPDFGenerator().generate(pdf_context, pdf_path)
                state.pdf.generated = True
                state.pdf.path = str(generated_path)
                state.pdf.url = f"{reverse('devis-generate', kwargs={'pk': devis_request.id})}?format=pdf"
            except Exception as exc:
                logger.exception(
                    "PDF generation failed for request_id=%s: %s",
                    getattr(devis_request, "id", None),
                    exc,
                )
                state.pdf.generated = False
                state.pdf.path = None
                state.pdf.url = None

            state.metadata.status = "processed"

            return state, {
                "request_id": devis_request.id,
                "status": "processed",
                "estimate": formatted_payload.get("estimate", {}),
                "quote": formatted_payload.get("quote", {}),
                "pdf_url": state.pdf.url,
                "clarification_questions": [],
                "selected_features": state.planning.selected_features,
            }
        except Exception as exc:
            logger.exception(
                "Devis orchestrator failed for request_id=%s: %s",
                getattr(devis_request, "id", None),
                exc,
            )
            state.metadata.errors.append("Unable to process this devis request right now.")
            state.metadata.status = "failed"
            return state, {
                "request_id": devis_request.id,
                "status": "failed",
                "detail": "Could not generate devis. Please try again.",
                "estimate": {},
                "quote": {},
                "pdf_url": None,
                "clarification_questions": [],
                "selected_features": state.planning.selected_features,
            }

    def _build_clarification_payload(self, devis_request, state: AgentState) -> dict:
        return {
            "request_id": devis_request.id,
            "status": "needs_clarification",
            "estimate": {},
            "quote": {
                "included_groups": [],
                "optional_items": [],
                "recurring_items": [],
                "totals": {
                    "included_min": 0,
                    "included_max": 0,
                    "optional_min": 0,
                    "optional_max": 0,
                    "recurring_min": 0,
                    "recurring_max": 0,
                    "grand_total_min": 0,
                    "grand_total_max": 0,
                },
                "notes": [],
                "missing_information": state.validation.missing_fields,
            },
            "pdf_url": None,
            "clarification_questions": state.validation.clarification_questions,
            "selected_features": state.planning.selected_features,
        }

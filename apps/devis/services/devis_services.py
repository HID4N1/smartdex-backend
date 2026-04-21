from apps.devis.models import DevisRequest
from core.pricing.service import DevisService as CoreDevisService
from apps.devis.presentation.formatter import format_generated_quote

class DevisService:
    def __init__(self):
        self.pricing_service = CoreDevisService()

    def _build_pipeline_hints(self, devis_request: DevisRequest) -> dict:
        return {
            "budget_range": devis_request.budget_range,
            "timeline": devis_request.timeline,
            "project_type": devis_request.project_type,
            "preferred_language": devis_request.preferred_language,
            "features": devis_request.features or [],
        }

    def generate_quote_from_request(self, devis_request: DevisRequest) -> dict:
        hints = self._build_pipeline_hints(devis_request)

        pipeline_result = self.pricing_service.generate_devis(
            description=devis_request.description,
            project_type_hint=devis_request.project_type or None,
            selected_features=devis_request.features or None,
            budget_hint=devis_request.budget_range or None,
            deadline_hint=devis_request.timeline or None,
        )

        devis_request.status = "processed"
        devis_request.save(update_fields=["status", "updated_at"])

        return format_generated_quote(devis_request, pipeline_result)
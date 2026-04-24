from __future__ import annotations

import logging
from pathlib import Path

from apps.devis.agents.orchestrator import DevisOrchestrator
from apps.devis.models import DevisRequest

logger = logging.getLogger(__name__)


class DevisService:
    def __init__(self):
        self.orchestrator = DevisOrchestrator()

    def create_request_from_description(
        self,
        *,
        description: str,
        client_name: str = "",
        client_email: str = "",
        client_phone: str = "",
        preferred_language: str = "",
    ) -> DevisRequest:
        return DevisRequest.objects.create(
            description=description,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            preferred_language=preferred_language,
        )

    def generate_quote_from_request(self, devis_request: DevisRequest) -> dict:
        state, response_payload = self.orchestrator.run(devis_request)

        new_status = state.metadata.status
        valid_statuses = {choice for choice, _ in DevisRequest.STATUS_CHOICES}
        if new_status in valid_statuses and devis_request.status != new_status:
            devis_request.status = new_status
            devis_request.save(update_fields=["status", "updated_at"])
        elif new_status not in valid_statuses:
            logger.info(
                "Skipping unsupported request status transition for request_id=%s: %s",
                devis_request.id,
                new_status,
            )

        if response_payload.get("status") == "failed":
            logger.error(
                "Devis generation failed for request_id=%s; errors=%s",
                devis_request.id,
                state.metadata.errors,
            )

        return response_payload

    def get_pdf_file_path(self, devis_request: DevisRequest) -> Path | None:
        pdf_name = f"devis_{devis_request.id}.pdf"
        temp_path = Path("/tmp") / pdf_name
        if temp_path.exists():
            return temp_path
        return None

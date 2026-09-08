from __future__ import annotations

from typing import Any

from apps.devis.models import DevisRequest
from core.utils.privacy import redact_for_ai, redact_pii_text


class DevisAIInputBuilder:
    """Build the whitelisted project context allowed to cross the LLM boundary."""

    @staticmethod
    def build_project_context(devis_request: DevisRequest) -> dict[str, Any]:
        known_sensitive_values = [
            getattr(devis_request, "client_name", None),
            getattr(devis_request, "client_email", None),
            getattr(devis_request, "client_phone", None),
            getattr(devis_request, "access_token", None),
        ]

        # OpenAI receives this AI-safe project context, not full client metadata.
        return {
            "description": redact_pii_text(
                getattr(devis_request, "description", "") or "",
                known_sensitive_values,
            ),
            "project_type": getattr(devis_request, "project_type", "") or None,
            "features": redact_for_ai(
                getattr(devis_request, "features", []) or [],
                known_sensitive_values,
            ),
            "budget_range": redact_pii_text(
                getattr(devis_request, "budget_range", "") or "",
                known_sensitive_values,
            ) or None,
            "timeline": redact_pii_text(
                getattr(devis_request, "timeline", "") or "",
                known_sensitive_values,
            ) or None,
            "preferred_language": getattr(devis_request, "preferred_language", "") or None,
            "extra_hints": redact_for_ai(
                getattr(devis_request, "extra_hints", {}) or {},
                known_sensitive_values,
            ),
        }

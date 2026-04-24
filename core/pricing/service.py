from core.pricing.extractor import ProjectSpecExtractor
from core.pricing.normalizer import normalize_project_spec
from core.pricing.estimator import estimate_project
from core.pricing.quote_builder import build_quote


class DevisService:
    def __init__(self):
        self.extractor = ProjectSpecExtractor()

    def generate_from_normalized_spec(
        self,
        *,
        normalized_spec: dict,
        description: str,
        project_type_hint: str | None = None,
        selected_features: list[str] | None = None,
        budget_hint: str | None = None,
        deadline_hint: str | None = None,
        extracted_spec: dict | None = None,
    ) -> dict:
        estimate = estimate_project(normalized_spec)
        quote = build_quote(normalized_spec)

        return {
            "input": {
                "description": description,
                "project_type_hint": project_type_hint,
                "selected_features": selected_features or [],
                "budget_hint": budget_hint,
                "deadline_hint": deadline_hint,
            },
            "extracted_spec": extracted_spec or {},
            "normalized_spec": normalized_spec,
            "estimate": estimate,
            "quote": quote,
        }

    def generate_devis(
        self,
        description: str,
        project_type_hint: str | None = None,
        selected_features: list[str] | None = None,
        budget_hint: str | None = None,
        deadline_hint: str | None = None,
    ) -> dict:
        extracted_spec = self.extractor.extract(
            description=description,
            project_type_hint=project_type_hint,
            selected_features=selected_features,
            budget_hint=budget_hint,
            deadline_hint=deadline_hint,
        )

        normalized_spec = normalize_project_spec(extracted_spec)
        return self.generate_from_normalized_spec(
            normalized_spec=normalized_spec,
            description=description,
            project_type_hint=project_type_hint,
            selected_features=selected_features,
            budget_hint=budget_hint,
            deadline_hint=deadline_hint,
            extracted_spec=extracted_spec.model_dump(),
        )

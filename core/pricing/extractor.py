from django.conf import settings

from core.ai.provider import (
    AIMalformedResponseError,
    AIOperationRunner,
    build_chat_model,
    enforce_input_limit,
)
from core.pricing.extractor_schema import ExtractedProjectSpec
from core.utils.privacy import redact_pii_text


SYSTEM_PROMPT = """
You are a project requirement extraction assistant for Smartdex.

Your job is to read a non-technical user request and convert it into a structured project specification.

Rules:
- Extract the most likely project type.
- Normalize features into short internal labels.
- Infer integrations only when clearly stated or strongly implied.
- Estimate complexity conservatively.
- If something is unclear, mark it as unknown or add it to missing_information.
- Do not invent unnecessary features.
- Prefer business interpretation over technical jargon.
- Return only structured data that matches the schema.
"""

USER_PROMPT_TEMPLATE = """
User request:
{description}

Optional structured hints:
project_type_hint: {project_type_hint}
selected_features: {selected_features}
budget_hint: {budget_hint}
deadline_hint: {deadline_hint}
"""


class ProjectSpecExtractor:
    def __init__(self, model: str | None = None, ai_runner=None):
        self.model = model or settings.OPENAI_CHAT_MODEL
        self.ai_runner = ai_runner or AIOperationRunner()
        self.llm = build_chat_model(
            model=self.model,
            temperature=0,
            max_output_tokens=settings.OPENAI_STRUCTURED_MAX_OUTPUT_TOKENS,
        )

        self.structured_llm = self.llm.with_structured_output(
            ExtractedProjectSpec,
            method="json_schema",
        )

    def extract(
        self,
        description: str,
        project_type_hint: str | None = None,
        selected_features: list[str] | None = None,
        budget_hint: str | None = None,
        deadline_hint: str | None = None,
    ) -> ExtractedProjectSpec:
        selected_features = selected_features or []

        prompt = (
            SYSTEM_PROMPT.strip()
            + "\n\n"
            + USER_PROMPT_TEMPLATE.format(
                description=redact_pii_text(description.strip()),
                project_type_hint=project_type_hint or "unknown",
                selected_features=", ".join(selected_features) if selected_features else "none",
                budget_hint=redact_pii_text(budget_hint) or "unknown",
                deadline_hint=redact_pii_text(deadline_hint) or "unknown",
            ).strip()
        )

        enforce_input_limit(prompt)

        def request():
            result = self.structured_llm.invoke(prompt)
            if not isinstance(result, ExtractedProjectSpec):
                try:
                    return ExtractedProjectSpec.model_validate(result)
                except Exception:
                    raise AIMalformedResponseError() from None
            return result

        return self.ai_runner.run(
            operation="pricing_project_extraction",
            model=self.model,
            call=request,
        )

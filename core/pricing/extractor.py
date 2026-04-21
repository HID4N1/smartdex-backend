from langchain_openai import ChatOpenAI

from core.pricing.extractor_schema import ExtractedProjectSpec


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
    def __init__(self, model: str = "gpt-4.1-mini"):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
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
                description=description.strip(),
                project_type_hint=project_type_hint or "unknown",
                selected_features=", ".join(selected_features) if selected_features else "none",
                budget_hint=budget_hint or "unknown",
                deadline_hint=deadline_hint or "unknown",
            ).strip()
        )

        result = self.structured_llm.invoke(prompt)
        return result
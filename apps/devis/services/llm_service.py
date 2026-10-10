from __future__ import annotations

from django.conf import settings
from pydantic import BaseModel, ValidationError

from core.ai.provider import (
    AIConfigurationError,
    AIMalformedResponseError,
    AIOperationRunner,
    AIProviderError,
    build_chat_model,
    enforce_input_limit,
)


class LLMService:
    def __init__(self, model: str | None = None, ai_runner=None):
        self.model = model or settings.OPENAI_CHAT_MODEL
        self.api_key = settings.OPENAI_API_KEY
        self.ai_runner = ai_runner or AIOperationRunner()

    def _build_client(self, temperature: float = 0.0):
        if not self.api_key:
            return None

        try:
            return build_chat_model(
                model=self.model,
                temperature=temperature,
                max_output_tokens=settings.OPENAI_STRUCTURED_MAX_OUTPUT_TOKENS,
                api_key=self.api_key,
            )
        except AIConfigurationError:
            return None

    def extract_structured_json(self, *, prompt: str, schema: type[BaseModel], fallback: BaseModel) -> BaseModel:
        client = self._build_client(temperature=0)
        if client is None:
            return fallback

        enforce_input_limit(prompt)

        def request():
            structured = client.with_structured_output(schema, method="json_schema")
            result = structured.invoke(prompt)
            if isinstance(result, schema):
                return result
            try:
                return schema.model_validate(result)
            except ValidationError:
                raise AIMalformedResponseError() from None

        try:
            return self.ai_runner.run(
                operation="devis_requirement_extraction",
                model=self.model,
                call=request,
            )
        except AIProviderError:
            return fallback

    def generate_quote_text(self, *, prompt: str, fallback: dict) -> dict:
        client = self._build_client(temperature=0.2)
        if client is None:
            return fallback

        enforce_input_limit(prompt)

        def request():
            structured = client.with_structured_output(dict, method="json_schema")
            result = structured.invoke(prompt)
            if not isinstance(result, dict):
                raise AIMalformedResponseError()
            return result

        try:
            result = self.ai_runner.run(
                operation="devis_quote_narrative",
                model=self.model,
                call=request,
            )
            return {
                "title": self._safe_text(result.get("title"), fallback.get("title", "")),
                "summary": self._safe_text(result.get("summary"), fallback.get("summary", "")),
                "recommendation": self._safe_text(
                    result.get("recommendation"), fallback.get("recommendation", "")
                ),
                "commercial_notes": self._safe_text_list(
                    result.get("commercial_notes"), fallback.get("commercial_notes", [])
                ),
                "next_steps": self._safe_text_list(
                    result.get("next_steps"), fallback.get("next_steps", [])
                ),
            }
        except AIProviderError:
            return fallback

    @staticmethod
    def _safe_text(value, fallback: str) -> str:
        if not isinstance(value, str) or not value.strip():
            return fallback
        return value.strip()[:2000]

    @staticmethod
    def _safe_text_list(value, fallback: list) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return fallback
        cleaned = [item.strip()[:500] for item in value[:10] if item.strip()]
        return cleaned or fallback

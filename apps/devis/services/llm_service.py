from __future__ import annotations

import os

from django.conf import settings
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError


class LLMService:
    def __init__(self, model: str | None = None):
        self.model = model or getattr(settings, "OPENAI_CHAT_MODEL", None) or os.getenv("OPENAI_CHAT_MODEL") or "gpt-4.1-mini"
        self.api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")

    def _build_client(self, temperature: float = 0.0) -> ChatOpenAI | None:
        if not self.api_key:
            return None

        try:
            return ChatOpenAI(model=self.model, temperature=temperature, api_key=self.api_key)
        except Exception:
            return None

    def extract_structured_json(self, *, prompt: str, schema: type[BaseModel], fallback: BaseModel) -> BaseModel:
        client = self._build_client(temperature=0)
        if client is None:
            return fallback

        try:
            structured = client.with_structured_output(schema, method="json_schema")
            result = structured.invoke(prompt)
            if isinstance(result, schema):
                return result
            return schema.model_validate(result)
        except (ValidationError, Exception):
            return fallback

    def generate_quote_text(self, *, prompt: str, fallback: dict) -> dict:
        client = self._build_client(temperature=0.2)
        if client is None:
            return fallback

        try:
            structured = client.with_structured_output(dict, method="json_schema")
            result = structured.invoke(prompt)
            if not isinstance(result, dict):
                return fallback
            return {
                "title": result.get("title") or fallback.get("title", ""),
                "summary": result.get("summary") or fallback.get("summary", ""),
                "recommendation": result.get("recommendation") or fallback.get("recommendation", ""),
                "commercial_notes": result.get("commercial_notes") or fallback.get("commercial_notes", []),
                "next_steps": result.get("next_steps") or fallback.get("next_steps", []),
            }
        except Exception:
            return fallback

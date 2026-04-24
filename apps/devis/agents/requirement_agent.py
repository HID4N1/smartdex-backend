from __future__ import annotations

import re

from apps.devis.prompts.requirement_prompt import build_requirement_prompt
from apps.devis.schemas.agent_state import AgentState
from apps.devis.schemas.requirement_schema import RequirementExtraction
from apps.devis.services.llm_service import LLMService
from core.pricing.normalizer import FEATURE_MAP, PROJECT_TYPE_MAP


class RequirementAgent:
    def __init__(self, llm_service: LLMService | None = None):
        self.llm_service = llm_service or LLMService()

    def run(self, state: AgentState) -> AgentState:
        fallback = self._heuristic_extract(state)
        prompt = build_requirement_prompt(
            state.input.user_message,
            state.input.client_info.model_dump(),
        )
        extraction = self.llm_service.extract_structured_json(
            prompt=prompt,
            schema=RequirementExtraction,
            fallback=fallback,
        )

        state.requirement.project_type = extraction.project_type or fallback.project_type
        state.requirement.features_requested = self._dedupe(extraction.detected_features or fallback.detected_features)
        state.requirement.constraints = self._build_constraints(extraction)
        state.requirement.budget_range = extraction.budget_range or None
        state.requirement.timeline = extraction.timeline or None
        state.requirement.preferred_language = extraction.preferred_language or None
        state.requirement.clarity_score = extraction.confidence_score
        state.requirement.raw_extraction = extraction.model_dump()
        return state

    def _heuristic_extract(self, state: AgentState) -> RequirementExtraction:
        message = state.input.user_message or ""
        lowered = message.lower()
        detected_features = []
        for raw_feature, normalized in FEATURE_MAP.items():
            if raw_feature in lowered and normalized not in detected_features:
                detected_features.append(normalized)

        project_type = None
        for raw_type in PROJECT_TYPE_MAP:
            needle = raw_type.replace("_", " ")
            if needle != "unknown" and needle in lowered:
                project_type = PROJECT_TYPE_MAP[raw_type]
                break

        budget_match = re.search(r"(?:budget|mad|dh|eur|usd|€|\$)[:\s-]*([^.\n]+)", message, re.IGNORECASE)
        timeline_match = re.search(r"(?:in|within|under)\s+([^.\n]+?(?:day|days|week|weeks|month|months))", message, re.IGNORECASE)
        language = None
        for candidate in ("french", "francais", "français", "english", "arabic"):
            if candidate in lowered:
                language = "fr" if candidate in {"french", "francais", "français"} else candidate[:2]
                break

        complexity_hint = "high" if len(detected_features) >= 6 else "medium" if len(detected_features) >= 3 else "low"

        missing_information = []
        if not project_type:
            missing_information.append("project_type")
        if not detected_features:
            missing_information.append("features")

        return RequirementExtraction(
            project_type=project_type,
            detected_features=detected_features,
            budget_range=budget_match.group(1).strip() if budget_match else None,
            timeline=timeline_match.group(1).strip() if timeline_match else None,
            client_name=state.input.client_info.name,
            client_email=state.input.client_info.email,
            client_phone=state.input.client_info.phone,
            preferred_language=language,
            complexity_hint=complexity_hint,
            missing_information=missing_information,
            confidence_score=0.45 if project_type or detected_features else 0.2,
        )

    def _build_constraints(self, extraction: RequirementExtraction) -> list[str]:
        constraints = []
        if extraction.budget_range:
            constraints.append(f"Budget: {extraction.budget_range}")
        if extraction.timeline:
            constraints.append(f"Timeline: {extraction.timeline}")
        if extraction.preferred_language:
            constraints.append(f"Language: {extraction.preferred_language}")
        return constraints

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return seen

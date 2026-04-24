from __future__ import annotations

from apps.devis.schemas.agent_state import AgentState
from apps.devis.schemas.planning_schema import PlanningResult
from core.pricing.catalog import QUOTE_CATALOG
from core.pricing.extractor_schema import ExtractedProjectSpec
from core.pricing.normalizer import INTEGRATION_MAP, PROJECT_TYPE_MAP, normalize_project_spec
from core.pricing.selector import select_components


class PlanningAgent:
    def run(self, state: AgentState) -> tuple[AgentState, dict]:
        extraction = state.requirement.raw_extraction or {}
        normalized_project_type = self._normalize_project_type(state.requirement.project_type)
        normalized_integrations = self._extract_integrations(state.input.user_message)
        spec = ExtractedProjectSpec(
            project_type=normalized_project_type,
            business_goal=state.input.user_message,
            features=state.requirement.features_requested,
            integrations=normalized_integrations,
            complexity=extraction.get("complexity_hint") or self._infer_complexity(state.requirement.features_requested),
            design_level="standard",
            urgency=self._infer_urgency(state.requirement.timeline),
            admin_dashboard_needed="admin_dashboard" in state.requirement.features_requested,
            user_accounts_needed="authentication" in state.requirement.features_requested,
            payment_needed="payments" in state.requirement.features_requested,
            notifications_needed="notifications" in state.requirement.features_requested,
            confidence=state.requirement.clarity_score or 0.0,
            missing_information=state.validation.missing_fields,
        )

        normalized_spec = normalize_project_spec(spec)
        selected_components = select_components(normalized_spec)
        grouped_features = self._group_components(selected_components)

        known_feature_keys = set(QUOTE_CATALOG.keys())
        normalized_features = set(normalized_spec.get("features", []))
        excluded_features = [feature for feature in state.requirement.features_requested if feature not in known_feature_keys and feature not in normalized_features]

        planning = PlanningResult(
            selected_features=[component["key"] for component in selected_components],
            grouped_features=grouped_features,
            complexity_level=normalized_spec.get("complexity", "unknown"),
            assumptions=self._build_assumptions(state),
            excluded_features=excluded_features,
        )

        state.planning.selected_features = planning.selected_features
        state.planning.feature_groups = planning.grouped_features
        state.planning.complexity_level = planning.complexity_level
        state.planning.assumptions = planning.assumptions
        state.planning.excluded_features = planning.excluded_features
        return state, normalized_spec

    def _group_components(self, components: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for component in components:
            grouped.setdefault(component.get("category", "optional"), []).append(component)
        return grouped

    def _build_assumptions(self, state: AgentState) -> list[str]:
        assumptions = [
            "Pricing is based on the currently expressed scope and standard SmartDex delivery assumptions.",
        ]
        if not state.requirement.timeline:
            assumptions.append("Timeline was not confirmed and was treated as standard urgency.")
        if not state.requirement.preferred_language:
            assumptions.append("Default commercial wording was used because no output language was explicitly confirmed.")
        return assumptions

    def _normalize_project_type(self, project_type: str | None) -> str:
        if not project_type:
            return "unknown"

        raw_value = project_type.strip().lower().replace("-", " ").replace("_", " ")
        if raw_value in PROJECT_TYPE_MAP:
            return PROJECT_TYPE_MAP[raw_value]

        compact_value = raw_value.replace(" ", "_")
        if compact_value in PROJECT_TYPE_MAP:
            return PROJECT_TYPE_MAP[compact_value]

        for candidate, normalized in PROJECT_TYPE_MAP.items():
            candidate_text = candidate.replace("_", " ")
            if raw_value == candidate_text or raw_value in candidate_text or candidate_text in raw_value:
                return normalized

        return "unknown"

    def _extract_integrations(self, message: str | None) -> list[str]:
        if not message:
            return []

        lowered = message.lower()
        integrations = []
        for raw_integration, normalized in INTEGRATION_MAP.items():
            if raw_integration in lowered and normalized not in integrations:
                integrations.append(normalized)
        return integrations

    def _infer_complexity(self, features: list[str]) -> str:
        if len(features) >= 6:
            return "high"
        if len(features) >= 3:
            return "medium"
        if features:
            return "low"
        return "unknown"

    def _infer_urgency(self, timeline: str | None) -> str:
        if not timeline:
            return "normal"
        timeline_lower = timeline.lower()
        if "week" in timeline_lower or "urgent" in timeline_lower:
            return "urgent"
        return "normal"

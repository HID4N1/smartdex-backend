from __future__ import annotations

from apps.devis.schemas.agent_state import AgentState


class ValidationAgent:
    def run(self, state: AgentState) -> AgentState:
        description = (state.input.user_message or "").strip()
        project_type = state.requirement.project_type
        features = state.requirement.features_requested

        has_meaningful_description = len(description.split()) >= 5
        is_minimum_valid = bool(project_type or features or has_meaningful_description)

        missing_fields = []
        clarification_questions = []

        if not project_type:
            missing_fields.append("project_type")
            clarification_questions.append("What type of project do you want us to build: website, SaaS, web app, mobile app, or another format?")
        if not features:
            missing_fields.append("features")
            clarification_questions.append("Which core features do you need in the first version?")
        if not has_meaningful_description:
            missing_fields.append("description")
            clarification_questions.append("Can you describe the business goal or main workflow the solution should cover?")

        needs_clarification = not is_minimum_valid or len(missing_fields) >= 2

        state.validation.is_valid = is_minimum_valid and not needs_clarification
        state.validation.needs_clarification = needs_clarification
        state.validation.missing_fields = missing_fields
        state.validation.clarification_questions = clarification_questions[:3]
        state.validation.errors = []
        return state

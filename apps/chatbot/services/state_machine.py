from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ConversationState(str, Enum):
    GREETING = "GREETING"
    WAIT_FOR_PROJECT = "WAIT_FOR_PROJECT"
    DISCOVERY = "DISCOVERY"
    QUALIFICATION = "QUALIFICATION"
    SERVICE_SELECTION = "SERVICE_SELECTION"
    RECOMMENDATION = "RECOMMENDATION"
    OBJECTION_HANDLING = "OBJECTION_HANDLING"
    PRICING = "PRICING"
    LEAD_CAPTURE = "LEAD_CAPTURE"
    HANDOFF = "HANDOFF"


@dataclass(frozen=True)
class StatePolicy:
    objective: str
    allowed_actions: List[str]
    forbidden_actions: List[str]
    next_question: str


STATE_POLICIES: Dict[ConversationState, StatePolicy] = {
    ConversationState.GREETING: StatePolicy(
        objective="Welcome the user without starting qualification.",
        allowed_actions=["greet", "brief_identity", "wait_for_project"],
        forbidden_actions=["qualification", "pricing", "quote", "package_recommendation"],
        next_question="Que souhaitez-vous réaliser aujourd'hui ?",
    ),
    ConversationState.WAIT_FOR_PROJECT: StatePolicy(
        objective="Handle greetings, small talk, and general questions until a project request exists.",
        allowed_actions=["greet", "answer_general_question", "present_services_briefly", "wait_for_project"],
        forbidden_actions=["qualification", "pricing", "quote", "package_recommendation"],
        next_question="Que souhaitez-vous réaliser aujourd'hui ?",
    ),
    ConversationState.DISCOVERY: StatePolicy(
        objective="Understand the business, project goal, and problem to solve.",
        allowed_actions=["ask_business_type", "ask_project_goal"],
        forbidden_actions=["pricing", "quote", "package_recommendation"],
        next_question="What is the main goal you want this system to achieve?",
    ),
    ConversationState.QUALIFICATION: StatePolicy(
        objective="Collect scope signals before recommending a solution.",
        allowed_actions=["ask_project_type", "ask_features", "ask_budget", "ask_timeline"],
        forbidden_actions=["quote", "exact_pricing"],
        next_question="Which features are essential for the first version?",
    ),
    ConversationState.SERVICE_SELECTION: StatePolicy(
        objective="Match the qualified need to a SmartDex service.",
        allowed_actions=["service_match", "explain_fit", "ask_confirmation"],
        forbidden_actions=["quote", "unsupported_services"],
        next_question="Do you want to start with a focused MVP or a more complete version?",
    ),
    ConversationState.RECOMMENDATION: StatePolicy(
        objective="Recommend the best package and next step.",
        allowed_actions=["recommend_package", "recommend_next_step", "ask_confirmation"],
        forbidden_actions=["invented_features", "exact_pricing"],
        next_question="Would you like us to shape this as an MVP first?",
    ),
    ConversationState.OBJECTION_HANDLING: StatePolicy(
        objective="Handle hesitation while protecting SmartDex positioning.",
        allowed_actions=["reassure", "phase_scope", "explain_value"],
        forbidden_actions=["discount_promises", "arguing"],
        next_question="What is the main concern for you right now: budget, timing, or scope?",
    ),
    ConversationState.PRICING: StatePolicy(
        objective="Explain official pricing only when enough qualification exists.",
        allowed_actions=["explain_official_range", "explain_price_drivers", "ask_missing_scope"],
        forbidden_actions=["calculate_in_prompt", "invent_prices", "fixed_price"],
        next_question="What timeline do you have in mind for the first version?",
    ),
    ConversationState.LEAD_CAPTURE: StatePolicy(
        objective="Collect handoff details after the need is clear.",
        allowed_actions=["ask_contact_detail", "summarize_need"],
        forbidden_actions=["pressure", "contractual_promises"],
        next_question="What is the best email or phone number for follow-up?",
    ),
    ConversationState.HANDOFF: StatePolicy(
        objective="Prepare the conversation for a human SmartDex follow-up.",
        allowed_actions=["summarize", "confirm_next_step"],
        forbidden_actions=["new_scope", "new_price"],
        next_question="Should SmartDex prepare a short discovery call based on this scope?",
    ),
}


class SalesStateMachine:
    pricing_words = {
        "price", "pricing", "cost", "budget", "quote", "estimate", "devis",
        "prix", "cout", "couts", "tarif", "tarification", "combien", "estimation",
    }
    objection_words = {
        "expensive", "cher", "trop cher", "budget", "cheap", "moins cher",
        "not sure", "pas sur", "hesitate", "hesitation",
    }
    handoff_words = {
        "contact", "call", "meeting", "demo", "email", "phone", "whatsapp",
        "rendez-vous", "appel",
    }

    def normalize(self, text: str) -> str:
        return " ".join((text or "").lower().replace("'", " ").split())

    def choose_state(
        self,
        *,
        query: str,
        facts: Dict,
        history: Optional[List[Dict]] = None,
    ) -> ConversationState:
        history = history or []
        q = self.normalize(query)
        history_text = self.normalize(
            " ".join(msg.get("content", "") for msg in history[-8:])
        )
        has_active_project = bool(facts.get("has_active_project"))

        if not has_active_project:
            return ConversationState.WAIT_FOR_PROJECT

        if any(word in q for word in self.handoff_words) and facts.get("recommended_package"):
            return ConversationState.LEAD_CAPTURE

        if any(word in q for word in self.objection_words) and history:
            return ConversationState.OBJECTION_HANDLING

        if any(word in q for word in self.pricing_words):
            if self._has_pricing_inputs(facts):
                return ConversationState.PRICING
            return ConversationState.DISCOVERY

        if not history:
            return ConversationState.DISCOVERY

        if not facts.get("business_type") or not facts.get("project_goal"):
            return ConversationState.DISCOVERY

        if not facts.get("project_type") or not facts.get("features"):
            return ConversationState.QUALIFICATION

        if not self._service_was_presented(history_text):
            return ConversationState.SERVICE_SELECTION

        if not self._package_was_presented(history_text):
            return ConversationState.RECOMMENDATION

        return ConversationState.LEAD_CAPTURE

    def policy_for(self, state: ConversationState) -> StatePolicy:
        return STATE_POLICIES[state]

    def _has_pricing_inputs(self, facts: Dict) -> bool:
        return bool(
            facts.get("project_type")
            and (facts.get("features") or facts.get("project_goal"))
        )

    def _service_was_presented(self, history_text: str) -> bool:
        signals = [
            "smartdex can guide you toward",
            "smartdex would recommend",
            "recommend",
            "recommended service",
        ]
        return any(signal in history_text for signal in signals)

    def _package_was_presented(self, history_text: str) -> bool:
        signals = ["launch mvp", "growth system", "scale platform", "custom scope"]
        return any(signal in history_text for signal in signals)

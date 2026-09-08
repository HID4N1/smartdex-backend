from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional
import unicodedata

from core.pricing.estimator import estimate_project
from core.pricing.quote_builder import build_quote
from core.pricing.config import BASE_PRICE_RANGES
from core.pricing.normalizer import FEATURE_MAP, INTEGRATION_MAP


class QualificationNotAllowed(RuntimeError):
    pass


SUPPORTED_SERVICES = {
    "website": "Website Development",
    "webapp": "Custom Web Application",
    "saas": "SaaS Development",
    "mobile_app": "Mobile Application",
    "ecommerce": "E-commerce System",
    "ai_system": "AI Solution",
    "automation": "Business Automation",
    "dashboard": "Data Analytics Dashboard",
    "data_visualization": "Data Analytics Dashboard",
    "api_integration": "API Integration",
    "crm": "CRM System",
    "erp": "ERP System",
    "booking_system": "Booking and Reservation System",
    "content_management_system": "Content Management System",
}

SERVICE_FAMILY_LABELS = {
    "website_development": "Website Development",
    "ai_solution": "AI Solution",
    "business_automation": "Business Automation",
    "operational_system": "Custom Web Application",
}

PROJECT_LABELS = {
    "showcase_website": "site vitrine",
    "ecommerce": "site e-commerce",
    "showcase_with_catalog": "site vitrine avec catalogue",
    "booking_system": "système de réservation",
    "ai_chatbot": "chatbot IA",
    "ai_assistant": "assistant IA",
    "ai_automation": "automatisation par IA",
    "website": "site web",
}

PACKAGE_RULES = [
    ("launch", "Launch MVP", 0, 30000),
    ("growth", "Growth System", 30001, 100000),
    ("scale", "Scale Platform", 100001, 10_000_000),
]

PROJECT_KEYWORDS = {
    "ecommerce": ["ecommerce", "e-commerce", "online store", "shop", "boutique"],
    "booking_system": ["booking", "reservation", "appointment", "rendez-vous", "calendar"],
    "saas": ["saas", "subscription", "multi tenant", "platform"],
    "ai_system": ["ai", "chatbot", "assistant", "rag", "intelligence"],
    "automation": ["automation", "automate", "workflow", "automatisation", "automatiser"],
    "dashboard": ["dashboard", "analytics", "reporting", "kpi", "data"],
    "crm": ["crm", "client management", "customer management"],
    "erp": ["erp", "operations management"],
    "mobile_app": ["mobile app", "ios", "android"],
    "website": ["website", "site web", "landing page", "showcase", "vitrine"],
    "webapp": ["web app", "application web", "portal", "internal tool", "system"],
}

AI_SIGNALS = [
    "ia",
    "ai",
    "intelligence artificielle",
    "chatbot",
    "assistant intelligent",
    "assistant ia",
    "analyse automatique",
    "ocr",
    "agent ia",
    "machine learning",
]

CORRECTION_SIGNALS = [
    "non",
    "ce n est pas",
    "ce n'est pas",
    "je voulais dire",
    "seulement",
    "juste",
    "plutot",
    "plutôt",
    "pas de",
    "sans",
]

PROJECT_INTENT_SIGNALS = [
    "je veux",
    "je voudrais",
    "je cherche",
    "nous cherchons",
    "nous avons besoin",
    "nous souhaitons",
    "j ai besoin",
    "besoin d",
    "i need",
    "we need",
    "need a",
    "need an",
    "looking for",
    "projet",
    "site web",
    "website",
    "application mobile",
    "application web",
    "erp",
    "crm",
    "chatbot",
    "solution digitale",
    "automatiser",
    "automatiser notre entreprise",
    "booking website",
]

PROJECT_OBJECT_SIGNALS = [
    "site web",
    "website",
    "booking website",
    "booking",
    "reservation",
    "site vitrine",
    "vitrine",
    "erp",
    "crm",
    "application mobile",
    "application web",
    "chatbot",
    "solution digitale",
    "automatiser",
    "automatisation",
]

GREETING_ONLY_SIGNALS = {"bonjour", "salut", "bonsoir", "hello", "hi"}
THANKS_ONLY_SIGNALS = {"merci", "merci beaucoup", "thanks", "thank you"}

LEGAL_STRUCTURES = {
    "sa": "SA",
    "sarl": "SARL",
    "auto entrepreneur": "auto_entrepreneur",
    "auto-entrepreneur": "auto_entrepreneur",
    "association": "association",
}

INDUSTRY_KEYWORDS = {
    "car_rental": [
        "location de voiture",
        "location automobile",
        "agence de location",
        "loueur automobile",
        "location de vehicules",
        "location de vehicule",
        "auto rental",
        "car rental",
    ],
    "cosmetics": ["cosmetique", "cosmetiques", "cosmetics"],
    "restaurant": ["restaurant", "restauration"],
    "clinic": ["clinique", "clinic", "medical"],
    "retail": ["commerce", "retail", "magasin"],
    "services": ["services"],
}

QUESTION_LABELS = {
    "industry": "Quel est le secteur ou le type d'activité de votre entreprise ?",
    "project_type": "Souhaitez-vous un site vitrine, une boutique en ligne, une application web ou une autre solution ?",
    "product_catalog_required": "Souhaitez-vous afficher un catalogue de produits sur le site, sans vente en ligne ?",
    "branding_available": "Avez-vous déjà votre logo et vos contenus ?",
    "number_of_pages": "Combien de pages souhaitez-vous prévoir pour votre site vitrine ?",
    "timeline": "Quel délai souhaitez-vous pour mettre votre site en ligne ?",
    "budget": "Avez-vous une enveloppe budgétaire à respecter pour ce projet ?",
    "primary_objective": "Quel est le principal objectif de votre projet ?",
    "requested_features": "Quelles fonctionnalités sont essentielles pour la première version ?",
}

DEFAULT_STRUCTURED_STATE = {
    "language": "fr",
    "current_state": "WAIT_FOR_PROJECT",
    "has_active_project": False,
    "prequalification_intent": None,
    "just_activated_project": False,
    "industry": None,
    "business_activity": None,
    "legal_structure": None,
    "requested_solution": None,
    "project_type": None,
    "requested_features": [],
    "rejected_features": [],
    "primary_objective": None,
    "service_family": None,
    "complexity": None,
    "last_asked_field": None,
    "last_completed_field": None,
    "asked_fields": [],
    "completed_fields": [],
    "invalidated_fields": [],
    "missing_relevant_fields": [],
    "correction_history": [],
}


@dataclass
class SalesDecision:
    facts: Dict
    recommended_service: Optional[str] = None
    recommended_package: Optional[str] = None
    recommended_next_step: str = ""
    pricing: Optional[Dict] = None
    quote: Optional[Dict] = None
    missing_information: List[str] = field(default_factory=list)


class BusinessLogicEngine:
    def initial_state(self, structured_state: Optional[Dict] = None) -> Dict:
        return self._base_state(structured_state)

    def analyze(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        structured_state: Optional[Dict] = None,
    ) -> SalesDecision:
        facts = self.extract_facts(
            query=query,
            history=history or [],
            structured_state=structured_state,
        )
        project_type = facts.get("project_type")

        if project_type in SUPPORTED_SERVICES:
            facts["recommended_service"] = SUPPORTED_SERVICES[project_type]
        elif facts.get("service_family") in SERVICE_FAMILY_LABELS:
            facts["recommended_service"] = SERVICE_FAMILY_LABELS[facts["service_family"]]

        missing = self._missing_information(facts)
        decision = SalesDecision(
            facts=facts,
            recommended_service=facts.get("recommended_service"),
            recommended_next_step=self._next_step(facts, missing),
            missing_information=missing,
        )

        if project_type in BASE_PRICE_RANGES and project_type != "unknown":
            normalized_spec = self._normalized_spec(facts)
            estimate = estimate_project(normalized_spec)
            quote = build_quote(normalized_spec)
            package = self._select_package(estimate["estimated_range_max"])

            decision.pricing = estimate
            decision.quote = quote
            decision.recommended_package = package
            decision.facts["recommended_package"] = package

        return decision

    def extract_facts(
        self,
        *,
        query: str,
        history: List[Dict],
        structured_state: Optional[Dict] = None,
    ) -> Dict:
        state, extraction = self.update_structured_state(
            query=query,
            previous_state=structured_state,
        )
        current_text = self._normalize_text(query)
        text = self._combined_user_text(query, history)
        if not state.get("has_active_project") and self.detect_project_intent(text):
            state["has_active_project"] = True
            state["project_type"] = self._detect_project_type(text)
            state["requested_solution"] = state["project_type"] if state["project_type"] != "unknown" else None
            self.recompute_derived_state(state)
        facts = {
            "language": state.get("language"),
            "has_active_project": state.get("has_active_project"),
            "prequalification_intent": state.get("prequalification_intent"),
            "just_activated_project": state.get("just_activated_project"),
            "industry": state.get("industry"),
            "business_activity": state.get("business_activity"),
            "business_type": state.get("business_activity") or state.get("industry") or self._extract_business_type(text),
            "legal_structure": state.get("legal_structure"),
            "requested_solution": state.get("requested_solution"),
            "project_goal": state.get("primary_objective") or self._extract_project_goal(query, text),
            "primary_objective": state.get("primary_objective"),
            "project_type": state.get("project_type") or self._detect_project_type(current_text),
            "features": list(state.get("requested_features") or self._detect_terms(text, FEATURE_MAP)),
            "requested_features": list(state.get("requested_features") or []),
            "rejected_features": list(state.get("rejected_features") or []),
            "service_family": state.get("service_family"),
            "integrations": self._detect_terms(text, INTEGRATION_MAP),
            "budget_hint": self._detect_budget(text),
            "timeline_hint": self._detect_timeline(text),
            "complexity": state.get("complexity") or self._detect_complexity(text),
            "design_level": self._detect_design_level(text),
            "urgency": self._detect_urgency(text),
            "structured_state": state,
            "extraction": extraction,
            "completed_fields": list(state.get("completed_fields") or []),
            "missing_relevant_fields": list(state.get("missing_relevant_fields") or []),
            "last_asked_field": state.get("last_asked_field"),
            "next_question": self.next_question_for(state),
        }
        return facts

    def update_structured_state(
        self,
        *,
        query: str,
        previous_state: Optional[Dict] = None,
    ) -> tuple[Dict, Dict]:
        state = self._base_state(previous_state)
        state["just_activated_project"] = False
        extraction = self.extract_semantic_updates(query)
        updates = extraction["detected_updates"]
        correction = extraction["correction_intent"]
        if updates.get("has_active_project") and state.get("has_active_project"):
            updates["just_activated_project"] = False

        if correction:
            self._apply_correction_policy(state, updates, query)

        for field_name, value in updates.items():
            if value is None:
                continue
            if field_name == "requested_features":
                for feature in value:
                    self._add_unique(state, "requested_features", feature)
                    self._remove_value(state, "rejected_features", feature)
            elif field_name == "rejected_features":
                for feature in value:
                    self._add_unique(state, "rejected_features", feature)
                    self._remove_value(state, "requested_features", feature)
            else:
                previous = state.get(field_name)
                if previous and previous != value:
                    state["correction_history"].append(
                        {"field": field_name, "from": previous, "to": value, "source": query}
                    )
                state[field_name] = value

        if updates:
            asked = state.get("asked_fields") or []
            last_asked = state.get("last_asked_field")
            extraction["answered_requested_field"] = bool(last_asked and last_asked in updates)
            if last_asked and last_asked not in asked:
                asked.append(last_asked)
                state["asked_fields"] = asked

        self.recompute_derived_state(state)
        return state, extraction

    def trace_message_processing(
        self,
        *,
        query: str,
        previous_state: Optional[Dict] = None,
    ) -> Dict:
        state_before = self._base_state(previous_state)
        extraction = self.extract_semantic_updates(query)
        state_after, applied_extraction = self.update_structured_state(
            query=query,
            previous_state=previous_state,
        )
        next_field = (state_after.get("missing_relevant_fields") or [None])[0]
        return {
            "incoming": query,
            "detected_intent": extraction.get("prequalification_intent")
            or extraction.get("detected_updates", {}).get("prequalification_intent"),
            "extracted_entities": extraction.get("detected_updates", {}),
            "normalized_values": {
                key: value
                for key, value in extraction.get("detected_updates", {}).items()
                if key in {"industry", "project_type", "requested_solution", "legal_structure"}
            },
            "state_before": state_before,
            "merge_result": state_after,
            "recomputed_state": state_after,
            "completed_fields": state_after.get("completed_fields", []),
            "missing_fields": state_after.get("missing_relevant_fields", []),
            "selected_next_field": next_field,
            "applied_extraction": applied_extraction,
        }

    def extract_semantic_updates(self, query: str) -> Dict:
        text = self._normalize_text(query)
        had_project = False
        updates: Dict[str, object] = {
            "prequalification_intent": self.detect_prequalification_intent(text),
        }

        if self.detect_project_intent(text):
            had_project = True
            updates["has_active_project"] = True
            updates["just_activated_project"] = True

        if self._has_showcase_signal(text):
            updates["requested_solution"] = "showcase_website"
            updates["project_type"] = "showcase_website"
            updates["primary_objective"] = "present_business"
        elif "site web" in text or "website" in text:
            updates["requested_solution"] = "website"
            updates["project_type"] = "website"

        if self._has_online_sales_signal(text):
            updates.setdefault("requested_features", [])
            updates["requested_features"].append("online_sales")
            if not self._has_showcase_signal(text):
                updates["requested_solution"] = "ecommerce"
                updates["project_type"] = "ecommerce"

        if self._has_booking_signal(text):
            updates.setdefault("requested_features", [])
            updates["requested_features"].append("booking_feature")
            updates["requested_solution"] = "booking_system"
            updates["project_type"] = "booking_system"

        if self._has_operational_management_signal(text):
            updates.setdefault("requested_features", [])
            updates["requested_features"].append("operational_management_feature")

        if "erp" in text:
            updates["requested_solution"] = "erp"
            updates["project_type"] = "erp"

        if "crm" in text:
            updates["requested_solution"] = "crm"
            updates["project_type"] = "crm"

        if "application mobile" in text:
            updates["requested_solution"] = "mobile_app"
            updates["project_type"] = "mobile_app"

        if any(term in text for term in ["automatiser", "automatisation"]) and not self._has_explicit_ai_signal(text):
            updates["requested_solution"] = "automation"
            updates["project_type"] = "automation"

        ai_project = self._detect_explicit_ai_project(text)
        if ai_project:
            updates["project_type"] = ai_project
            updates["requested_solution"] = ai_project
            updates.setdefault("requested_features", [])
            updates["requested_features"].append("ai_solution")

        industry = self._detect_industry(text)
        if industry:
            updates["industry"] = industry
            if industry == "cosmetics":
                updates["business_activity"] = "vente de produits cosmétiques"

        legal_structure = self._detect_legal_structure(text)
        if legal_structure:
            updates["legal_structure"] = legal_structure

        return {
            "detected_updates": updates,
            "answered_requested_field": False,
            "correction_intent": self._detect_correction_intent(text),
            "project_intent": had_project,
        }

    def recompute_derived_state(self, state: Dict) -> None:
        rejected = set(state.get("rejected_features") or [])
        requested = [f for f in state.get("requested_features") or [] if f not in rejected]
        state["requested_features"] = requested

        if "ai_solution" in rejected and state.get("service_family") == "ai_solution":
            state["service_family"] = None

        if state.get("requested_solution") == "showcase_website":
            state["project_type"] = "showcase_website"
        elif "online_sales" in requested and "online_sales" not in rejected:
            state["project_type"] = "ecommerce"

        if self._project_has_explicit_ai(state.get("project_type")) or "ai_solution" in requested:
            state["service_family"] = "ai_solution"
        elif state.get("project_type") in {"showcase_website", "website", "ecommerce", "showcase_with_catalog"}:
            state["service_family"] = "website_development"
        elif state.get("project_type") == "booking_system":
            state["service_family"] = "operational_system"

        if state.get("project_type") == "showcase_website":
            state["complexity"] = "basic"
        elif state.get("project_type") == "ecommerce":
            state["complexity"] = "medium"

        previous_completed = set(state.get("completed_fields") or [])
        state["completed_fields"] = self.calculate_completed_fields(state)
        newly_completed = [
            field_name
            for field_name in state["completed_fields"]
            if field_name not in previous_completed
        ]
        if newly_completed:
            state["last_completed_field"] = newly_completed[-1]
        if state.get("has_active_project"):
            state["missing_relevant_fields"] = self.select_missing_relevant_fields(state)
        else:
            state["missing_relevant_fields"] = []

    def calculate_completed_fields(self, state: Dict) -> List[str]:
        completed = []
        invalidated = set(state.get("invalidated_fields") or [])
        validators = {
            "industry": lambda value: value in set(INDUSTRY_KEYWORDS.keys()),
            "project_type": lambda value: value in {
                "showcase_website", "website", "ecommerce", "showcase_with_catalog",
                "booking_system", "ai_chatbot", "ai_assistant", "ai_automation",
            },
            "legal_structure": lambda value: value in set(LEGAL_STRUCTURES.values()),
            "requested_solution": lambda value: bool(value),
            "primary_objective": lambda value: bool(value),
        }
        for field_name, validator in validators.items():
            value = state.get(field_name)
            if value and field_name not in invalidated and validator(value):
                completed.append(field_name)
        return completed

    def select_missing_relevant_fields(self, state: Dict) -> List[str]:
        if not state.get("has_active_project"):
            raise QualificationNotAllowed(
                "Qualification cannot run before project intent."
            )

        project_type = state.get("project_type")
        if project_type == "showcase_website":
            required = [
                "industry",
                "project_type",
                "product_catalog_required",
                "branding_available",
                "number_of_pages",
                "timeline",
                "budget",
            ]
        elif project_type == "ecommerce":
            required = ["industry", "project_type", "requested_features", "timeline", "budget"]
        elif state.get("service_family") == "ai_solution":
            required = ["industry", "project_type", "primary_objective", "requested_features", "timeline", "budget"]
        else:
            required = ["industry", "project_type", "primary_objective", "requested_features", "timeline"]

        completed = set(state.get("completed_fields") or [])
        missing = [
            field_name
            for field_name in required
            if field_name not in completed
        ]
        if missing:
            assert missing[0] not in completed
        return missing

    def next_question_for(self, state: Dict) -> str:
        if not state.get("has_active_project"):
            return "Comment puis-je vous aider aujourd’hui ?"
        fields = state.get("missing_relevant_fields") or self.select_missing_relevant_fields(state)
        if not fields:
            return "Quel délai souhaitez-vous pour mettre votre site en ligne ?"
        return QUESTION_LABELS.get(fields[0], "Quel détail souhaitez-vous préciser en priorité ?")

    def set_last_asked_field(self, state: Dict, question: str) -> Dict:
        next_state = self._base_state(state)
        field_name = self._field_for_question(question, next_state)
        if field_name:
            next_state["last_asked_field"] = field_name
            self._add_unique(next_state, "asked_fields", field_name)
        return next_state

    def _combined_text(self, query: str, history: List[Dict]) -> str:
        messages = [msg.get("content", "") for msg in history[-8:]]
        messages.append(query)
        return " ".join(messages).lower()

    def _combined_user_text(self, query: str, history: List[Dict]) -> str:
        messages = [
            msg.get("content", "")
            for msg in history[-8:]
            if msg.get("role") == "user"
        ]
        messages.append(query)
        return self._normalize_text(" ".join(messages))

    def _detect_project_type(self, text: str) -> str:
        if self._has_showcase_signal(text):
            return "showcase_website"
        if self._has_online_sales_signal(text):
            return "ecommerce"
        if self._has_booking_signal(text):
            return "booking_system"
        ai_project = self._detect_explicit_ai_project(text)
        if ai_project:
            return ai_project
        for project_type, keywords in PROJECT_KEYWORDS.items():
            if project_type == "ai_system" and not self._has_explicit_ai_signal(text):
                continue
            if any(keyword in text for keyword in keywords):
                return project_type
        return "unknown"

    def detect_project_intent(self, text: str) -> bool:
        text = self._normalize_text(text)
        if self.detect_prequalification_intent(text) in {
            "greeting",
            "thanks",
            "small_talk",
            "company_question",
            "services_question",
            "help_question",
        }:
            return False

        has_request = any(signal in text for signal in PROJECT_INTENT_SIGNALS)
        has_project_object = any(signal in text for signal in PROJECT_OBJECT_SIGNALS)
        return has_request and has_project_object

    def detect_prequalification_intent(self, text: str) -> str:
        text = self._normalize_text(text)
        if text in GREETING_ONLY_SIGNALS:
            return "greeting"
        if text in THANKS_ONLY_SIGNALS:
            return "thanks"
        if any(term in text for term in ["ca va", "comment allez vous", "comment vas tu"]):
            return "small_talk"
        if any(term in text for term in ["qui etes vous", "qui es tu", "que faites vous"]):
            return "company_question"
        if any(term in text for term in ["quels services proposez vous", "vos services", "services proposez"]):
            return "services_question"
        if text in {"pouvez vous m aider", "pouvez-vous m aider", "tu peux m aider"}:
            return "help_question"
        return "project" if self.detect_project_intent_candidate(text) else "general"

    def detect_project_intent_candidate(self, text: str) -> bool:
        return any(signal in text for signal in PROJECT_OBJECT_SIGNALS)

    def _detect_terms(self, text: str, mapping: Dict[str, str]) -> List[str]:
        terms = []
        for keyword, canonical in mapping.items():
            if keyword in text and canonical not in terms:
                terms.append(canonical)
        return terms

    def _extract_business_type(self, text: str) -> str:
        markers = ["business is", "company is", "we are a", "i run a", "je suis", "mon business"]
        for marker in markers:
            if marker in text:
                fragment = text.split(marker, 1)[1].strip()
                return " ".join(fragment.split()[:6]).strip(".,")
        return ""

    def _extract_project_goal(self, query: str, text: str) -> str:
        if any(word in text for word in ["automate", "automation", "automatiser"]):
            return "Reduce manual work through automation."
        if any(word in text for word in ["sell", "vendre", "shop", "boutique"]):
            return "Sell products or services online."
        if any(word in text for word in ["booking", "reservation", "appointment"]):
            return "Manage bookings and appointments more efficiently."
        if any(word in text for word in ["dashboard", "analytics", "kpi"]):
            return "Track business performance with better visibility."
        if len(query.split()) > 5:
            return query.strip()
        return ""

    def _detect_budget(self, text: str) -> str:
        if any(marker in text for marker in ["mad", "dh", "dirham", "budget"]):
            return "mentioned"
        return ""

    def _detect_timeline(self, text: str) -> str:
        if any(marker in text for marker in ["urgent", "asap", "quick", "rapid", "this month", "deadline"]):
            return "urgent"
        if any(marker in text for marker in ["week", "month", "mois", "semaine"]):
            return "mentioned"
        return ""

    def _detect_complexity(self, text: str) -> str:
        high = ["multi-user", "multi user", "real-time", "realtime", "erp", "marketplace", "complex"]
        medium = ["dashboard", "payments", "roles", "integration", "api", "notifications"]
        if any(term in text for term in high):
            return "high"
        if any(term in text for term in medium):
            return "medium"
        return "unknown"

    def _detect_design_level(self, text: str) -> str:
        if any(term in text for term in ["premium", "custom ui", "animation", "brand"]):
            return "premium"
        if any(term in text for term in ["professional", "modern", "responsive"]):
            return "standard"
        return "unknown"

    def _detect_urgency(self, text: str) -> str:
        if any(term in text for term in ["urgent", "asap", "quick", "rapid", "tight deadline"]):
            return "urgent"
        return "normal"

    def _missing_information(self, facts: Dict) -> List[str]:
        if not facts.get("has_active_project"):
            return []
        if facts.get("missing_relevant_fields"):
            return facts["missing_relevant_fields"]
        missing = []
        if not facts.get("business_type"):
            missing.append("business type")
        if not facts.get("project_goal"):
            missing.append("project goal")
        if not facts.get("project_type") or facts.get("project_type") == "unknown":
            missing.append("project type")
        if not facts.get("features"):
            missing.append("essential features")
        if not facts.get("timeline_hint"):
            missing.append("timeline")
        return missing

    def _normalized_spec(self, facts: Dict) -> Dict:
        return {
            "project_type": self._pricing_project_type(facts.get("project_type", "unknown")),
            "business_goal": facts.get("project_goal", ""),
            "features": facts.get("features", []),
            "integrations": facts.get("integrations", []),
            "complexity": facts.get("complexity", "unknown"),
            "design_level": facts.get("design_level", "unknown"),
            "urgency": facts.get("urgency", "normal"),
            "confidence": 0.75,
            "missing_information": self._missing_information(facts),
        }

    def _select_package(self, estimated_max: int) -> str:
        for _, label, minimum, maximum in PACKAGE_RULES:
            if minimum <= estimated_max <= maximum:
                return label
        return "Custom Scope"

    def _next_step(self, facts: Dict, missing: List[str]) -> str:
        if facts.get("next_question"):
            return facts["next_question"]
        if missing:
            return f"Clarify {missing[0]}."
        if facts.get("project_type") in SUPPORTED_SERVICES:
            return "Confirm MVP scope and prepare a structured discovery."
        return "Clarify the project type before recommending a solution."

    def _base_state(self, previous_state: Optional[Dict]) -> Dict:
        state = deepcopy(DEFAULT_STRUCTURED_STATE)
        if previous_state:
            for key, value in previous_state.items():
                if key in state:
                    state[key] = deepcopy(value)
        for list_key in [
            "requested_features",
            "rejected_features",
            "asked_fields",
            "completed_fields",
            "invalidated_fields",
            "missing_relevant_fields",
            "correction_history",
        ]:
            state[list_key] = list(state.get(list_key) or [])
        return state

    def _normalize_text(self, text: str) -> str:
        text = (text or "").lower().replace("’", "'").replace("`", "'")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-z0-9'\-\s]", " ", text)
        return " ".join(text.split())

    def _detect_correction_intent(self, text: str) -> bool:
        return any(signal in text for signal in CORRECTION_SIGNALS)

    def _apply_correction_policy(self, state: Dict, updates: Dict, query: str) -> None:
        if updates.get("project_type") == "showcase_website":
            for feature in ["online_sales", "ecommerce", "ai_solution"]:
                self._add_unique(state, "rejected_features", feature)
                self._remove_value(state, "requested_features", feature)
            if state.get("project_type") not in {None, "showcase_website"}:
                state["correction_history"].append(
                    {"field": "project_type", "from": state.get("project_type"), "to": "showcase_website", "source": query}
                )
            state["project_type"] = "showcase_website"
            state["requested_solution"] = "showcase_website"
            state["service_family"] = "website_development"
            self._add_unique(state, "invalidated_fields", "requested_features")
        elif "rejected_features" in updates:
            for feature in updates["rejected_features"]:
                self._add_unique(state, "rejected_features", feature)
                self._remove_value(state, "requested_features", feature)

    def _has_showcase_signal(self, text: str) -> bool:
        return any(term in text for term in ["site vitrine", "simple vitrine", "vitrine", "showcase website", "showcase"])

    def _has_online_sales_signal(self, text: str) -> bool:
        return any(term in text for term in ["vente en ligne", "vendre en ligne", "boutique en ligne", "paiement en ligne", "e-commerce", "ecommerce"])

    def _has_booking_signal(self, text: str) -> bool:
        return any(term in text for term in ["reservation en ligne", "réservation en ligne", "rendez-vous en ligne", "booking"])

    def _has_operational_management_signal(self, text: str) -> bool:
        return any(term in text for term in ["gestion de flotte", "gestion operationnelle", "operations management"])

    def _has_explicit_ai_signal(self, text: str) -> bool:
        phrase_signals = [
            signal for signal in AI_SIGNALS
            if signal not in {"ai", "ia", "ocr"}
        ]
        if any(signal in text for signal in phrase_signals):
            return True
        return any(re.search(rf"\b{signal}\b", text) for signal in ["ai", "ia", "ocr"])

    def _detect_explicit_ai_project(self, text: str) -> Optional[str]:
        if "chatbot" in text:
            return "ai_chatbot"
        if any(term in text for term in ["assistant ia", "assistant intelligent", "agent ia"]):
            return "ai_assistant"
        if any(term in text for term in ["automatisation par ia", "intelligence artificielle", "machine learning", "ocr", "analyse automatique"]):
            return "ai_automation"
        return None

    def _detect_industry(self, text: str) -> Optional[str]:
        for canonical, keywords in INDUSTRY_KEYWORDS.items():
            if any(term in text for term in keywords):
                return canonical
        return None

    def _detect_legal_structure(self, text: str) -> Optional[str]:
        for keyword, canonical in LEGAL_STRUCTURES.items():
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return canonical
        return None

    def _project_has_explicit_ai(self, project_type: Optional[str]) -> bool:
        return project_type in {"ai_system", "ai_chatbot", "ai_assistant", "ai_automation"}

    def _add_unique(self, state: Dict, field_name: str, value: str) -> None:
        values = state.setdefault(field_name, [])
        if value not in values:
            values.append(value)

    def _remove_value(self, state: Dict, field_name: str, value: str) -> None:
        state[field_name] = [item for item in state.get(field_name, []) if item != value]

    def _field_for_question(self, question: str, state: Dict) -> Optional[str]:
        for field_name, label in QUESTION_LABELS.items():
            if label == question:
                return field_name
        fields = state.get("missing_relevant_fields") or []
        return fields[0] if fields else None

    def _pricing_project_type(self, project_type: str) -> str:
        if project_type == "showcase_website":
            return "website"
        if project_type in {"ai_chatbot", "ai_assistant", "ai_automation"}:
            return "ai_system"
        return project_type

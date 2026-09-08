import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.chatbot.services.business_logic import SUPPORTED_SERVICES


QUESTION_FIELD_TERMS = {
    "industry": [
        "secteur d'activité",
        "secteur ou le type d'activité",
        "type d'activité",
    ],
    "legal_structure": ["statut juridique", "forme juridique", "type d'entreprise"],
    "budget": ["budget", "enveloppe budgétaire"],
    "timeline": ["délai", "timeline", "mettre en ligne"],
    "project_type": ["site vitrine", "boutique en ligne", "application web", "autre solution"],
    "primary_objective": ["principal objectif", "objectif de votre projet"],
    "requested_features": ["fonctionnalités", "fonctionnalites"],
}


@dataclass
class ValidationResult:
    valid: bool
    reasons: List[str] = field(default_factory=list)


class ResponseValidator:
    question_pattern = re.compile(r"\?")
    price_pattern = re.compile(r"\b\d[\d\s,.]*(?:mad|dh|dirham|dirhams)\b", re.IGNORECASE)

    def validate(
        self,
        *,
        answer: str,
        decision: Dict,
        allow_pricing: bool,
        structured_state: Optional[Dict] = None,
    ) -> ValidationResult:
        reasons = []
        clean_answer = " ".join((answer or "").split())
        lower_answer = clean_answer.lower()
        structured_state = structured_state or decision.get("facts", {}).get("structured_state") or {}

        if not clean_answer:
            reasons.append("empty response")

        if len(self.question_pattern.findall(clean_answer)) > 1:
            reasons.append("more than one question")

        word_count = len(clean_answer.split())
        if word_count > 110:
            reasons.append("response too long")

        if self.price_pattern.search(clean_answer) and not allow_pricing:
            reasons.append("pricing mentioned before pricing is allowed")

        if self._contains_unsupported_service(clean_answer):
            reasons.append("unsupported service mentioned")

        if any(phrase in lower_answer for phrase in ["great question", "excellent choice", "as an ai"]):
            reasons.append("generic assistant tone")

        if not structured_state.get("has_active_project"):
            premature_terms = [
                "statut juridique",
                "forme juridique",
                "secteur d'activité",
                "secteur ou le type d'activité",
                "budget",
                "enveloppe budgétaire",
                "délai",
                "timeline",
                "taille de votre entreprise",
                "combien d'employés",
            ]
            if "?" in lower_answer and any(term in lower_answer for term in premature_terms):
                reasons.append("qualification before project intent")

        if "intelligence artificielle" in lower_answer or "système d'intelligence artificielle" in lower_answer or "système d’intelligence artificielle" in lower_answer:
            if structured_state.get("service_family") != "ai_solution":
                reasons.append("ai mentioned without confirmed ai intent")

        if structured_state.get("project_type") == "showcase_website":
            forbidden = [
                "système d'intelligence artificielle",
                "système d’intelligence artificielle",
                "ce système",
                "scale platform",
                "custom_web_application",
            ]
            if any(term in lower_answer for term in forbidden):
                reasons.append("internal or generic system wording for showcase website")

        if "online_sales" in structured_state.get("rejected_features", []) or "ecommerce" in structured_state.get("rejected_features", []):
            if any(term in lower_answer for term in ["vente en ligne", "e-commerce", "ecommerce", "boutique en ligne", "paiement en ligne"]):
                reasons.append("rejected ecommerce mentioned")

        if "legal_structure" in structured_state.get("completed_fields", []):
            legal_question_terms = ["type d'entreprise", "statut juridique", "forme juridique", "sarl", "sa"]
            if "?" in lower_answer and any(term in lower_answer for term in legal_question_terms):
                reasons.append("asks completed legal structure")

        asked_field = self._detect_question_field(lower_answer)
        completed_fields = set(structured_state.get("completed_fields") or [])
        invalidated_fields = set(structured_state.get("invalidated_fields") or [])
        if asked_field and asked_field in completed_fields and asked_field not in invalidated_fields:
            reasons.append(f"asks completed field: {asked_field}")

        last_completed_field = structured_state.get("last_completed_field")
        if asked_field and asked_field == last_completed_field and asked_field not in invalidated_fields:
            reasons.append(f"asks last completed field: {asked_field}")

        if structured_state.get("project_type") == "showcase_website":
            legal_question_terms = ["type d'entreprise", "statut juridique", "forme juridique", "sarl", "sa"]
            if "?" in lower_answer and any(term in lower_answer for term in legal_question_terms):
                reasons.append("asks irrelevant legal structure")

        return ValidationResult(valid=not reasons, reasons=reasons)

    def build_fallback(
        self,
        *,
        state_policy: Dict,
        decision: Dict,
        allow_pricing: bool,
        structured_state: Optional[Dict] = None,
    ) -> str:
        structured_state = structured_state or decision.get("facts", {}).get("structured_state") or {}
        if not structured_state.get("has_active_project"):
            return self._build_prequalification_fallback(structured_state)

        deterministic = self._build_state_fallback(structured_state)
        if deterministic:
            return deterministic

        service = decision.get("recommended_service")
        package = decision.get("recommended_package")
        pricing = decision.get("pricing") if allow_pricing else None
        missing = decision.get("missing_information") or []
        question = state_policy.get("next_question") or "What should we clarify first?"

        if pricing:
            return (
                f"For this scope, SmartDex would position it as {package or 'a custom package'} "
                f"around {pricing['estimated_range_min']} - {pricing['estimated_range_max']} MAD, "
                f"depending on the confirmed features and complexity. {question}"
            )

        if service and package and not missing:
            return (
                f"For your case, SmartDex would recommend {service} as a {package}. "
                f"The next step is to confirm the MVP scope before discussing a precise range. {question}"
            )

        if service:
            return (
                f"For this need, SmartDex can guide you toward {service}, but we should qualify the scope first. "
                f"{question}"
            )

        return (
            "I can help shape this into the right SmartDex solution, but I need one detail first. "
            f"{question}"
        )

    def _build_state_fallback(self, state: Dict) -> str:
        if not state:
            return ""

        project_type = state.get("project_type")
        industry = state.get("industry")
        missing = state.get("missing_relevant_fields") or []
        next_field = missing[0] if missing else None

        if state.get("just_activated_project") and next_field == "industry":
            return "Très bien.\n\nQuel est votre secteur d'activité ?"

        if project_type == "showcase_website" and industry == "cosmetics":
            rejected = set(state.get("rejected_features") or [])
            questions = {
                "product_catalog_required": (
                    "Souhaitez-vous afficher un catalogue de produits sur le site ?"
                    if "online_sales" in rejected
                    else "Souhaitez-vous afficher un catalogue de produits sur le site, sans vente en ligne ?"
                ),
                "branding_available": "Avez-vous déjà votre logo et vos contenus ?",
                "number_of_pages": "Combien de pages souhaitez-vous prévoir pour votre site vitrine ?",
                "timeline": "Quel délai souhaitez-vous pour mettre votre site en ligne ?",
                "budget": "Avez-vous une enveloppe budgétaire à respecter pour ce projet ?",
            }
            return questions.get(next_field) or "Quel délai souhaitez-vous pour mettre votre site vitrine en ligne ?"

        if project_type == "ecommerce":
            return "Souhaitez-vous que le site permette réellement l'achat en ligne avec paiement, ou plutôt seulement présenter les produits ?"

        if project_type == "showcase_website":
            if next_field == "industry":
                return "Quel est le secteur ou le type d'activité de votre entreprise ?"
            return "Avez-vous déjà votre logo et vos contenus pour le site vitrine ?"

        if next_field == "industry":
            return "Quel est le secteur ou le type d'activité de votre entreprise ?"
        if next_field == "project_type":
            return "Souhaitez-vous un site vitrine, une boutique en ligne, une application web ou une autre solution ?"
        if next_field == "primary_objective":
            return "Quel est le principal objectif de votre projet ?"
        if next_field == "requested_features":
            return "Quelles fonctionnalités sont essentielles pour la première version ?"
        if next_field == "timeline":
            return "Quel délai souhaitez-vous pour avancer sur ce projet ?"
        if next_field == "budget":
            return "Avez-vous une enveloppe budgétaire à respecter pour ce projet ?"
        return ""

    def _build_prequalification_fallback(self, state: Dict) -> str:
        intent = state.get("prequalification_intent")
        if intent == "greeting":
            return "Bonjour ! Comment puis-je vous aider aujourd’hui ?"
        if intent == "thanks":
            return "Avec plaisir. Que souhaitez-vous réaliser aujourd'hui ?"
        if intent == "small_talk":
            return "Je vais très bien, merci. Que souhaitez-vous réaliser aujourd'hui ?"
        if intent == "company_question":
            return (
                "SmartDex accompagne les entreprises dans la création de sites web, applications, CRM, ERP, "
                "automatisations et solutions IA. Que souhaitez-vous réaliser aujourd'hui ?"
            )
        if intent == "services_question":
            return (
                "SmartDex propose des sites web, applications web et mobiles, CRM, ERP, e-commerce, automatisation "
                "et solutions IA. Quel type de projet souhaitez-vous explorer ?"
            )
        return (
            "Je peux vous aider à clarifier un projet digital ou répondre à vos questions sur SmartDex. "
            "Que souhaitez-vous réaliser aujourd'hui ?"
        )

    def _contains_unsupported_service(self, answer: str) -> bool:
        lower_answer = answer.lower()
        risky_terms = ["blockchain", "crypto", "game development", "hardware", "legal services"]
        if any(term in lower_answer for term in risky_terms):
            return True

        service_names = [name.lower() for name in SUPPORTED_SERVICES.values()]
        known_terms = [
            "website", "web application", "saas", "ai", "automation", "dashboard",
            "e-commerce", "crm", "erp", "booking", "reservation", "api",
        ]
        return False if any(term in lower_answer for term in service_names + known_terms) else False

    def _detect_question_field(self, lower_answer: str) -> Optional[str]:
        if "?" not in lower_answer:
            return None
        for field_name, terms in QUESTION_FIELD_TERMS.items():
            if any(term in lower_answer for term in terms):
                return field_name
        return None

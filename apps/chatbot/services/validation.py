import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from apps.chatbot.services.business_logic import SUPPORTED_SERVICES


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
    ) -> ValidationResult:
        reasons = []
        clean_answer = " ".join((answer or "").split())

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

        if any(phrase in clean_answer.lower() for phrase in ["great question", "excellent choice", "as an ai"]):
            reasons.append("generic assistant tone")

        return ValidationResult(valid=not reasons, reasons=reasons)

    def build_fallback(
        self,
        *,
        state_policy: Dict,
        decision: Dict,
        allow_pricing: bool,
    ) -> str:
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

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.pricing.estimator import estimate_project
from core.pricing.quote_builder import build_quote
from core.pricing.config import BASE_PRICE_RANGES
from core.pricing.normalizer import FEATURE_MAP, INTEGRATION_MAP


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
    def analyze(self, query: str, history: Optional[List[Dict]] = None) -> SalesDecision:
        facts = self.extract_facts(query=query, history=history or [])
        project_type = facts.get("project_type")

        if project_type in SUPPORTED_SERVICES:
            facts["recommended_service"] = SUPPORTED_SERVICES[project_type]

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

    def extract_facts(self, *, query: str, history: List[Dict]) -> Dict:
        text = self._combined_text(query, history)
        facts = {
            "business_type": self._extract_business_type(text),
            "project_goal": self._extract_project_goal(query, text),
            "project_type": self._detect_project_type(text),
            "features": self._detect_terms(text, FEATURE_MAP),
            "integrations": self._detect_terms(text, INTEGRATION_MAP),
            "budget_hint": self._detect_budget(text),
            "timeline_hint": self._detect_timeline(text),
            "complexity": self._detect_complexity(text),
            "design_level": self._detect_design_level(text),
            "urgency": self._detect_urgency(text),
        }
        return facts

    def _combined_text(self, query: str, history: List[Dict]) -> str:
        messages = [msg.get("content", "") for msg in history[-8:]]
        messages.append(query)
        return " ".join(messages).lower()

    def _detect_project_type(self, text: str) -> str:
        for project_type, keywords in PROJECT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return project_type
        return "unknown"

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
            "project_type": facts.get("project_type", "unknown"),
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
        if missing:
            return f"Clarify {missing[0]}."
        if facts.get("project_type") in SUPPORTED_SERVICES:
            return "Confirm MVP scope and prepare a structured discovery."
        return "Clarify the project type before recommending a solution."

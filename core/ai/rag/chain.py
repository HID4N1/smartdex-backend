from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Optional
import logging
import os
import unicodedata

from openai import OpenAI

from apps.chatbot.services.business_logic import BusinessLogicEngine
from apps.chatbot.services.prompting import PromptBuilder
from apps.chatbot.services.state_machine import ConversationState, SalesStateMachine
from apps.chatbot.services.validation import ResponseValidator
from core.ai.rag.retriever import Retriever
from core.utils.privacy import redact_for_ai, redact_pii_text, sanitize_for_log
from core.utils.validators import sanitize_query


logger = logging.getLogger(__name__)


DEFAULT_PROMPT = """You are a Smartdex AI consultant specialized in SaaS, AI, automation, and digital systems.

You are acting like a real sales consultant helping a client.

STRICT RULES:
- Use ONLY the provided context
- Do NOT invent information
- Always give price ranges, never fixed prices
- If information is missing, say it clearly
- Keep answers natural and human
- Be helpful, clear, and business-oriented

CHAT HISTORY:
{history}

CONTEXT:
{context}

QUESTION:
{question}

INSTRUCTIONS:
- Answer like a human consultant
- Use the context to answer
- If the request is vague, ask 1 smart follow-up question
- Guide the user toward the right solution
"""


class RAGChain:
    def __init__(
        self,
        prompt_path: Optional[str] = None,
        top_k: int = 8,
        rerank_top_n: int = 4,
        model: str = "gpt-4.1-mini",
        max_distance: float = 1.8,
    ):
        self.retriever = Retriever()
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self.model = model
        self.max_distance = max_distance
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key or "missing-openai-api-key")
        self.prompt_template = self._load_prompt(prompt_path)
        self.business_logic = BusinessLogicEngine()
        self.state_machine = SalesStateMachine()
        self.prompt_builder = PromptBuilder()
        self.validator = ResponseValidator()

    def _load_prompt(self, path: Optional[str] = None) -> str:
        if path:
            prompt_file = Path(path)
            if prompt_file.exists() and prompt_file.is_file():
                return prompt_file.read_text(encoding="utf-8")

        default_path = Path(__file__).resolve().parent / "prompts" / "prompt_template.txt"
        if default_path.exists() and default_path.is_file():
            return default_path.read_text(encoding="utf-8")

        logger.warning("Prompt file not found. Falling back to DEFAULT_PROMPT.")
        return DEFAULT_PROMPT

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.lower()
        text = text.replace("’", "'").replace("`", "'")
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = " ".join(text.split())
        return text

    def _detect_intent(self, query: str) -> str:
        q = self._normalize_text(query)

        intent_keywords = {
            "pricing": [
                "price", "pricing", "cost", "quote", "budget", "how much", "estimate", "devis",
                "prix", "cout", "couts", "tarif", "tarification", "combien", "estimation",
            ],
            "technical": [
                "stack", "technology", "backend", "frontend", "api", "django", "react", "architecture",
                "database", "hosting", "deployment", "integrations",
                "technique", "technologie", "base de donnees", "hebergement", "deploiement",
            ],
            "company": [
                "who are you", "what do you do", "about", "company", "smartdex",
                "qui es tu", "qui etes vous", "que faites vous", "a propos", "societe", "entreprise",
            ],
            "services": [
                "service", "services", "build", "develop", "system", "platform", "website", "web app",
                "mobile app", "saas", "automation", "crm", "erp", "software", "solution",
                "site web", "application web", "application mobile", "plateforme", "logiciel",
                "automatiser", "automatisation", "j ai besoin", "je veux", "je souhaite",
                "ecommerce", "e-commerce", "site ecommerce", "site e commerce", "boutique en ligne",
            ],
        }

        scores = {k: 0 for k in intent_keywords.keys()}

        for intent, keywords in intent_keywords.items():
            for keyword in keywords:
                if keyword in q:
                    scores[intent] += 1

        best_intent = max(scores, key=scores.get)
        return best_intent if scores[best_intent] > 0 else "general"

    def _intent_filter(self, intent: str) -> Optional[Dict]:
        mapping = {
            "pricing": None,
            "technical": None,
            "services": None,
            "company": None,
            "general": None,
        }
        return mapping.get(intent)

    def _build_history_text(self, history: Optional[List[Dict]]) -> str:
        if not history:
            return "No previous conversation."

        lines = []
        for msg in history[-6:]:
            role = msg.get("role", "user").capitalize()
            content = redact_pii_text(msg.get("content", "").strip())
            if content:
                lines.append(f"{role}: {content}")

        return "\n".join(lines) if lines else "No previous conversation."

    def _rewrite_query_with_history(self, query: str, history: Optional[List[Dict]]) -> str:
        """
        Rewrite short follow-up messages into a standalone question using recent history.
        """
        if not self.api_key:
            return query

        if not history or len(query.split()) > 12:
            return query

        history_text = self._build_history_text(history)
        safe_query = redact_pii_text(query)

        prompt = f"""
You are rewriting a user's follow-up message into a standalone query for retrieval.

Conversation history:
{history_text}

Latest user message:
{safe_query}

Return only the rewritten standalone query.
If the latest message is already clear on its own, return it unchanged.
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Rewrite follow-up questions into standalone retrieval queries."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            rewritten = (response.choices[0].message.content or "").strip()
            return rewritten or query
        except Exception:
            return query

    def _filter_weak_docs(self, docs: List[Dict]) -> List[Dict]:
        filtered = []
        for doc in docs:
            distance = doc.get("distance")
            if distance is None or distance <= self.max_distance:
                filtered.append(doc)
        return filtered

    def _rerank(self, docs: List[Dict], query: str, max_docs: Optional[int] = None) -> List[Dict]:
        if not docs:
            return []

        if max_docs is None:
            max_docs = self.rerank_top_n

        query_terms = [term for term in self._normalize_text(query).split() if term.strip()]
        source_priority = {
            "01_identity.md": 13,
            "02_company.md": 12,
            "03_services.md": 12,
            "04_pricing.md": 14,
            "05_sales_playbook.md": 13,
            "06_qualification.md": 13,
            "07_objections.md": 11,
            "08_case_studies.md": 8,
            "09_process.md": 10,
            "10_faq.md": 9,
            "11_rules.md": 14,
            "pricing_guide.txt": 12,
            "pricing_breakdown.txt": 11,
            "rules.txt": 10,
            "qualification_flow.txt": 9,
            "services_detailed.txt": 8,
            "company_info.txt": 7,
            "sales_style.txt": 6,
            "objections.txt": 6,
            "faq.txt": 5,
            "use_cases.txt": 4,
            "knowledge_base.txt": 1,
        }

        def score(doc: Dict) -> tuple:
            text = self._normalize_text(doc.get("text", ""))
            metadata = doc.get("metadata", {})
            source = self._normalize_text(str(metadata.get("source", "")))
            raw_source = Path(str(metadata.get("source", ""))).name
            doc_type = self._normalize_text(str(metadata.get("doc_type", "")))
            distance = doc.get("distance")

            text_score = sum(term in text for term in query_terms)
            source_score = sum(term in source for term in query_terms)
            type_score = sum(term in doc_type for term in query_terms)
            priority_score = source_priority.get(raw_source, 0)
            distance_score = distance if distance is not None else 999999

            return (text_score + source_score + type_score, priority_score, -distance_score)

        ranked = sorted(docs, key=score, reverse=True)
        return ranked[:max_docs]

    def _build_context(self, docs: List[Dict]) -> str:
        context_blocks = []

        for doc in docs:
            metadata = doc.get("metadata", {})
            source = metadata.get("source", "unknown")
            chunk_index = metadata.get("chunk_index", "unknown")
            doc_type = metadata.get("doc_type", "unknown")
            text = doc.get("text", "").strip()

            if not text:
                continue

            block = f"[SOURCE: {source} | CHUNK: {chunk_index} | TYPE: {doc_type}]\n{text}"
            context_blocks.append(block)

        return "\n\n".join(context_blocks)

    def _build_prompt(self, history: str, context: str, question: str) -> str:
        return self.prompt_template.format(
            history=history,
            context=context,
            question=question,
        )

    def _generate(self, messages: List[Dict], temperature: float = 0.2) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            top_p=0.8,
            max_tokens=220,
        )
        return (response.choices[0].message.content or "").strip()

    def _generate_local_fallback(
        self,
        state_policy: Dict,
        decision: Dict,
        allow_pricing: bool,
        structured_state: Optional[Dict] = None,
    ) -> str:
        return self.validator.build_fallback(
            state_policy=state_policy,
            decision=decision,
            allow_pricing=allow_pricing,
            structured_state=structured_state,
        )

    def _serialize_decision(self, decision) -> Dict:
        data = asdict(decision)
        data["recommended_service"] = decision.recommended_service
        data["recommended_package"] = decision.recommended_package
        data["recommended_next_step"] = decision.recommended_next_step
        return data

    def _pricing_allowed(self, state: ConversationState, decision: Dict) -> bool:
        return state == ConversationState.PRICING and bool(decision.get("pricing"))

    def _prequalification_answer(self, intent: str) -> str:
        if intent == "greeting":
            return "Bonjour ! Comment puis-je vous aider aujourd’hui ?"
        if intent == "thanks":
            return "Avec plaisir. Comment puis-je vous aider aujourd’hui ?"
        if intent == "small_talk":
            return "Je vais très bien, merci. Comment puis-je vous aider aujourd’hui ?"
        if intent == "company_question":
            return (
                "SmartDex accompagne les entreprises dans leurs projets digitaux: sites web, "
                "applications, CRM, ERP, automatisation et solutions IA. Comment puis-je vous aider aujourd’hui ?"
            )
        if intent == "services_question":
            return (
                "SmartDex propose des sites web, applications web et mobiles, CRM, ERP, e-commerce, "
                "automatisation et solutions IA. Quel projet souhaitez-vous explorer ?"
            )
        return "Comment puis-je vous aider aujourd’hui ?"

    def _prequalification_result(
        self,
        *,
        clean_query: str,
        rewritten_query: str,
        intent: str,
        structured_state: Dict,
        response_source: str,
        conversation_id: Optional[str] = None,
        is_new_conversation: Optional[bool] = None,
    ) -> Dict:
        structured_state["current_state"] = ConversationState.WAIT_FOR_PROJECT.value
        structured_state["has_active_project"] = False
        structured_state["missing_relevant_fields"] = []
        structured_state["prequalification_intent"] = intent
        answer = self._prequalification_answer(intent)
        runtime_trace = {
            "conversation_id": conversation_id,
            "is_new_conversation": is_new_conversation,
            "loaded_state": structured_state,
            "current_state": ConversationState.WAIT_FOR_PROJECT.value,
            "has_active_project": False,
            "detected_intent": intent,
            "selected_handler": response_source,
            "qualification_selector_called": False,
            "response_source": response_source,
            "final_state": ConversationState.WAIT_FOR_PROJECT.value,
        }
        logger.info("chatbot_runtime_trace=%s", redact_for_ai(runtime_trace))
        return {
            "query": clean_query,
            "rewritten_query": rewritten_query,
            "intent": intent,
            "answer": answer,
            "sources": [],
            "context_used": "",
            "state": ConversationState.WAIT_FOR_PROJECT.value,
            "business_decision": {},
            "structured_state": structured_state,
            "runtime_trace": runtime_trace,
        }

    def run(
        self,
        query: str,
        history: Optional[List[Dict]] = None,
        structured_state: Optional[Dict] = None,
        conversation_id: Optional[str] = None,
        is_new_conversation: Optional[bool] = None,
    ) -> Dict:
        clean_query = sanitize_query(query)

        if not clean_query:
            return {
                "query": query,
                "intent": "unknown",
                "answer": "Please provide a valid question.",
                "sources": [],
                "context_used": "",
                "rewritten_query": query,
            }

        loaded_state = self.business_logic.initial_state(structured_state)
        rewritten_query = clean_query
        safe_clean_query = redact_pii_text(clean_query)
        prequalification_intent = self.business_logic.detect_prequalification_intent(clean_query)
        if prequalification_intent == "greeting" and not loaded_state.get("has_active_project"):
            return self._prequalification_result(
                clean_query=clean_query,
                rewritten_query=rewritten_query,
                intent="greeting",
                structured_state=loaded_state,
                response_source="greeting_handler",
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
            )

        if prequalification_intent == "small_talk" and not loaded_state.get("has_active_project"):
            return self._prequalification_result(
                clean_query=clean_query,
                rewritten_query=rewritten_query,
                intent="small_talk",
                structured_state=loaded_state,
                response_source="small_talk_handler",
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
            )

        if not loaded_state.get("has_active_project") and not self.business_logic.detect_project_intent(clean_query):
            return self._prequalification_result(
                clean_query=clean_query,
                rewritten_query=rewritten_query,
                intent=prequalification_intent,
                structured_state=loaded_state,
                response_source="wait_for_project_handler",
                conversation_id=conversation_id,
                is_new_conversation=is_new_conversation,
            )

        rewritten_query = self._rewrite_query_with_history(safe_clean_query, history)
        intent = self._detect_intent(rewritten_query)
        decision_obj = self.business_logic.analyze(
            clean_query,
            history=history or [],
            structured_state=loaded_state,
        )
        decision = self._serialize_decision(decision_obj)
        structured_state = decision.get("facts", {}).get("structured_state") or {}
        state = self.state_machine.choose_state(
            query=clean_query,
            facts=decision.get("facts", {}),
            history=history,
        )
        state_policy_obj = self.state_machine.policy_for(state)
        state_policy = asdict(state_policy_obj)
        allow_pricing = self._pricing_allowed(state, decision)
        qualification_selector_called = bool(structured_state.get("has_active_project"))
        structured_state["current_state"] = state.value

        if not allow_pricing:
            decision["pricing"] = None
            decision["quote"] = None

        deterministic_answer = self._generate_local_fallback(
            state_policy,
            decision,
            allow_pricing,
            structured_state=structured_state,
        )
        if deterministic_answer and (
            decision.get("missing_information")
            or not structured_state.get("has_active_project")
            or structured_state.get("just_activated_project")
        ):
            structured_state = self.business_logic.set_last_asked_field(
                structured_state,
                deterministic_answer,
            )
            decision["facts"]["structured_state"] = structured_state
            return {
                "query": clean_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "answer": deterministic_answer,
                "sources": [],
                "context_used": "",
                "state": state.value,
                "business_decision": decision,
                "structured_state": structured_state,
                "runtime_trace": {
                    "conversation_id": conversation_id,
                    "is_new_conversation": is_new_conversation,
                    "loaded_state": loaded_state,
                    "current_state": state.value,
                    "has_active_project": bool(structured_state.get("has_active_project")),
                    "detected_intent": intent,
                    "selected_handler": "deterministic_qualification_fallback",
                    "qualification_selector_called": qualification_selector_called,
                    "response_source": "deterministic_fallback",
                    "final_state": state.value,
                },
            }

        filter_metadata = self._intent_filter(intent)

        try:
            docs = self.retriever.search(
                redact_pii_text(rewritten_query),
                top_k=self.top_k,
                filter_metadata=filter_metadata,
            )
        except Exception as e:
            logger.error("Retriever failed: %s", sanitize_for_log(str(e)))
            return {
                "query": clean_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "answer": "I could not retrieve relevant information right now.",
                "sources": [],
                "context_used": "",
            }

        strong_docs = self._filter_weak_docs(docs)
        docs = strong_docs if strong_docs else docs[:3]
        docs = self._rerank(docs, rewritten_query)

        if not docs:
            return {
                "query": clean_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "answer": "I could not find enough relevant information to answer that accurately.",
                "sources": [],
                "context_used": "",
            }

        context = self._build_context(docs)
        messages = self.prompt_builder.build_messages(
            state=state.value,
            state_policy=state_policy,
            decision=decision,
            knowledge=context,
            history=history,
            user_message=safe_clean_query,
        )

        try:
            answer = self._generate(messages)
            validation = self.validator.validate(
                answer=answer,
                decision=decision,
                allow_pricing=allow_pricing,
                structured_state=structured_state,
            )
            if not validation.valid:
                repair_messages = messages + [
                    {
                        "role": "assistant",
                        "content": answer,
                    },
                    {
                        "role": "user",
                        "content": (
                            "Regenerate the response so it satisfies validation. "
                            f"Validation failures: {validation.reasons}. "
                            "Keep one question maximum and do not change business logic output."
                        ),
                    },
                ]
                answer = self._generate(repair_messages, temperature=0.1)
                validation = self.validator.validate(
                    answer=answer,
                    decision=decision,
                    allow_pricing=allow_pricing,
                    structured_state=structured_state,
                )
                if not validation.valid:
                    answer = self._generate_local_fallback(
                        state_policy,
                        decision,
                        allow_pricing,
                        structured_state=structured_state,
                    )
        except Exception as e:
            logger.warning(
                "LLM generation failed. Using local fallback answer: %s",
                sanitize_for_log(str(e)),
            )
            answer = self._generate_local_fallback(
                state_policy,
                decision,
                allow_pricing,
                structured_state=structured_state,
            )

        structured_state = self.business_logic.set_last_asked_field(structured_state, answer)
        structured_state["current_state"] = state.value
        decision["facts"]["structured_state"] = structured_state

        return {
            "query": clean_query,
            "rewritten_query": rewritten_query,
            "intent": intent,
            "answer": answer,
            "sources": [d.get("metadata", {}) for d in docs],
            "context_used": context,
            "state": state.value,
            "business_decision": decision,
            "structured_state": structured_state,
            "runtime_trace": {
                "conversation_id": conversation_id,
                "is_new_conversation": is_new_conversation,
                "loaded_state": loaded_state,
                "current_state": state.value,
                "has_active_project": bool(structured_state.get("has_active_project")),
                "detected_intent": intent,
                "selected_handler": "rag_llm",
                "qualification_selector_called": qualification_selector_called,
                "response_source": "llm_or_validated_fallback",
                "final_state": state.value,
            },
        }

from pathlib import Path
from typing import List, Dict, Optional
import logging
import os
import unicodedata

from openai import OpenAI

from core.ai.rag.retriever import Retriever
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
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.prompt_template = self._load_prompt(prompt_path)

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
            "pricing": {"doc_type": "pricing"},
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
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")

        return "\n".join(lines) if lines else "No previous conversation."

    def _rewrite_query_with_history(self, query: str, history: Optional[List[Dict]]) -> str:
        """
        Rewrite short follow-up messages into a standalone question using recent history.
        """
        if not history or len(query.split()) > 12:
            return query

        history_text = self._build_history_text(history)

        prompt = f"""
You are rewriting a user's follow-up message into a standalone query for retrieval.

Conversation history:
{history_text}

Latest user message:
{query}

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

        def score(doc: Dict) -> tuple:
            text = self._normalize_text(doc.get("text", ""))
            metadata = doc.get("metadata", {})
            source = self._normalize_text(str(metadata.get("source", "")))
            doc_type = self._normalize_text(str(metadata.get("doc_type", "")))
            distance = doc.get("distance")

            text_score = sum(term in text for term in query_terms)
            source_score = sum(term in source for term in query_terms)
            type_score = sum(term in doc_type for term in query_terms)
            distance_score = distance if distance is not None else 999999

            return (text_score + source_score + type_score, -distance_score)

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

    def _generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Smartdex AI assistant. Be accurate, grounded, natural, and sales-oriented.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.4,
        )
        return (response.choices[0].message.content or "").strip()

    def run(self, query: str, history: Optional[List[Dict]] = None) -> Dict:
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

        rewritten_query = self._rewrite_query_with_history(clean_query, history)
        intent = self._detect_intent(rewritten_query)
        filter_metadata = self._intent_filter(intent)

        try:
            docs = self.retriever.search(
                rewritten_query,
                top_k=self.top_k,
                filter_metadata=filter_metadata,
            )
        except Exception as e:
            logger.exception("Retriever failed: %s", e)
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

        history_text = self._build_history_text(history)
        context = self._build_context(docs)
        prompt = self._build_prompt(history_text, context, clean_query)

        try:
            answer = self._generate(prompt)
        except Exception as e:
            logger.exception("LLM generation failed: %s", e)
            return {
                "query": clean_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "answer": "I found relevant information, but I could not generate a response right now.",
                "sources": [d.get("metadata", {}) for d in docs],
                "context_used": context,
            }

        return {
            "query": clean_query,
            "rewritten_query": rewritten_query,
            "intent": intent,
            "answer": answer,
            "sources": [d.get("metadata", {}) for d in docs],
            "context_used": context,
        }
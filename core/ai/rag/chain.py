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

STRICT RULES:
- Use ONLY the provided context
- Do NOT invent information
- Always provide price ranges, never fixed prices
- If information is missing, say so clearly
- Keep answers structured and professional
- Do not prefix the answer with labels like "FINAL ANSWER"

CONTEXT:
{context}

QUESTION:
{question}

INSTRUCTIONS:
- Extract relevant information from the context
- Answer clearly and concisely
- If pricing is involved, explain factors affecting cost
- If multiple scenarios exist, mention them
- If the question is vague, guide the user toward the right next detail
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
                "combien ca coute", "combien cela coute", "budget projet", "budget site web"
            ],
            "technical": [
                "stack", "technology", "backend", "frontend", "api", "django", "react", "architecture",
                "database", "hosting", "deployment", "integrations", "technical",
                "technique", "technologie", "architecture technique", "base de donnees",
                "hebergement", "deploiement", "integration", "developpement technique"
            ],
            "company": [
                "who are you", "what do you do", "about", "company", "smartdex",
                "qui es tu", "qui etes vous", "qui es-tu", "qui etes-vous",
                "que faites vous", "que faites-vous", "a propos", "presentation",
                "societe", "entreprise", "agence", "qui est smartdex"
            ],
            "services": [
                "service", "services", "offer", "offering", "build", "develop", "development",
                "system", "platform", "booking", "dashboard", "website", "web app", "webapp",
                "mobile app", "saas", "automation", "automate", "crm", "erp", "software",
                "solution", "digital solution", "business system", "ecommerce", "e-commerce",
                "online store", "store", "marketplace",

                "site web", "application web", "application mobile", "plateforme",
                "solution saas", "solution digitale", "solution numerique", "outil digital",
                "logiciel", "systeme", "automatiser", "automatisation", "transformer mon activite",
                "digitaliser", "j ai besoin", "je veux", "je souhaite", "creer un site",
                "creer une plateforme", "developper une solution", "besoin d une solution",
                "besoin d un site", "besoin d une application", "pour mon activite",
                "pour mon entreprise", "pour mon business", "reservation", "prise de rendez vous",
                "site e commerce", "site ecommerce", "boutique en ligne", "vente en ligne"
            ],
        }

        scores = {
            "pricing": 0,
            "technical": 0,
            "company": 0,
            "services": 0,
        }

        for intent, keywords in intent_keywords.items():
            for keyword in keywords:
                if keyword in q:
                    scores[intent] += 1

        if "smartdex" in q and any(term in q for term in ["qui", "about", "a propos", "company", "entreprise"]):
            scores["company"] += 2

        if any(term in q for term in [
            "site web", "saas", "automatiser", "automation", "plateforme",
            "application", "ecommerce", "e-commerce", "boutique en ligne"
        ]):
            scores["services"] += 2

        if any(term in q for term in ["prix", "cout", "tarif", "budget", "devis", "combien"]):
            scores["pricing"] += 2

        if any(term in q for term in ["api", "django", "react", "backend", "frontend", "architecture"]):
            scores["technical"] += 2

        best_intent = max(scores, key=scores.get)

        if scores[best_intent] == 0:
            return "general"

        return best_intent

    def _intent_filter(self, intent: str) -> Optional[Dict]:
        mapping = {
            "pricing": {"doc_type": "pricing"},
            "technical": None,
            "services": None,
            "company": None,
            "general": None,
        }
        return mapping.get(intent)

    def _filter_weak_docs(self, docs: List[Dict]) -> List[Dict]:
        filtered = []

        for doc in docs:
            distance = doc.get("distance")
            if distance is None:
                filtered.append(doc)
                continue

            if distance <= self.max_distance:
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

            block = (
                f"[SOURCE: {source} | CHUNK: {chunk_index} | TYPE: {doc_type}]\n"
                f"{text}"
            )
            context_blocks.append(block)

        return "\n\n".join(context_blocks)

    def _build_prompt(self, context: str, question: str) -> str:
        return self.prompt_template.format(
            context=context,
            question=question,
        )

    def _generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a Smartdex AI assistant. Be accurate, grounded, and concise.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content or ""
        return content.strip()

    def run(self, query: str) -> Dict:
        clean_query = sanitize_query(query)

        if not clean_query:
            return {
                "query": query,
                "intent": "unknown",
                "answer": "Please provide a valid question.",
                "sources": [],
                "context_used": "",
            }

        intent = self._detect_intent(clean_query)
        filter_metadata = self._intent_filter(intent)

        logger.info("Chat query=%s", clean_query)
        logger.info("Detected intent=%s", intent)
        logger.info("Filter metadata=%s", filter_metadata)

        try:
            docs = self.retriever.search(
                clean_query,
                top_k=self.top_k,
                filter_metadata=filter_metadata,
            )
        except Exception as e:
            logger.exception("Retriever failed: %s", e)
            return {
                "query": clean_query,
                "intent": intent,
                "answer": "I could not retrieve relevant information right now.",
                "sources": [],
                "context_used": "",
            }

        strong_docs = self._filter_weak_docs(docs)

        if strong_docs:
            docs = strong_docs
        else:
            docs = docs[:3]

        docs = self._rerank(docs, clean_query)

        if not docs:
            return {
                "query": clean_query,
                "intent": intent,
                "answer": "I could not find enough relevant information to answer that accurately.",
                "sources": [],
                "context_used": "",
            }

        context = self._build_context(docs)
        prompt = self._build_prompt(context, clean_query)

        try:
            answer = self._generate(prompt)
        except Exception as e:
            logger.exception("LLM generation failed: %s", e)
            return {
                "query": clean_query,
                "intent": intent,
                "answer": "I found relevant information, but I could not generate a response right now.",
                "sources": [d.get("metadata", {}) for d in docs],
                "context_used": context,
            }

        logger.info("Sources=%s", [d.get("metadata", {}) for d in docs])
        logger.info("Answer length=%s", len(answer))

        return {
            "query": clean_query,
            "intent": intent,
            "answer": answer,
            "sources": [d.get("metadata", {}) for d in docs],
            "context_used": context,
        }
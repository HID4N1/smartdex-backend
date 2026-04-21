from pathlib import Path
from typing import List, Dict, Optional
import logging
import os

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
        top_k: int = 5,
        rerank_top_n: int = 3,
        model: str = "gpt-4.1-mini",
    ):
        self.retriever = Retriever()
        self.top_k = top_k
        self.rerank_top_n = rerank_top_n
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.prompt_template = self._load_prompt(prompt_path)

    def _load_prompt(self, path: Optional[str] = None) -> str:
        """
        Load prompt from provided path, then default file path, otherwise fallback to DEFAULT_PROMPT.
        """
        if path:
            prompt_file = Path(path)
            if prompt_file.exists() and prompt_file.is_file():
                return prompt_file.read_text(encoding="utf-8")

        default_path = Path(__file__).resolve().parent / "prompts" / "prompt_template.txt"
        if default_path.exists() and default_path.is_file():
            return default_path.read_text(encoding="utf-8")

        logger.warning("Prompt file not found. Falling back to DEFAULT_PROMPT.")
        return DEFAULT_PROMPT

    def _detect_intent(self, query: str) -> str:
        """
        Classify the user query into a lightweight intent bucket.
        """
        q = query.lower()

        pricing_keywords = ["price", "pricing", "cost", "quote", "budget", "how much", "devis", "estimate"]
        technical_keywords = ["stack", "technology", "backend", "frontend", "api", "django", "react", "architecture"]
        services_keywords = ["service", "offer", "build", "develop", "system", "platform", "booking", "dashboard"]
        company_keywords = ["who are you", "what do you do", "smartdex", "company", "about"]

        if any(k in q for k in pricing_keywords):
            return "pricing"
        if any(k in q for k in technical_keywords):
            return "technical"
        if any(k in q for k in company_keywords):
            return "company"
        if any(k in q for k in services_keywords):
            return "services"

        return "general"

    def _intent_filter(self, intent: str) -> Optional[Dict]:
        """
        Map intent to metadata filter.
        Requires `doc_type` metadata in your ingested chunks.
        """
        mapping = {
            "pricing": {"doc_type": "pricing"},
            "technical": {"doc_type": "technical"},
            "services": {"doc_type": "services"},
            "company": {"doc_type": "company"},
            "general": None,
        }
        return mapping.get(intent)

    def _rerank(self, docs: List[Dict], query: str, max_docs: Optional[int] = None) -> List[Dict]:
        """
        Lightweight reranking using keyword overlap.
        Keeps the strongest docs before prompt injection.
        """
        if not docs:
            return []

        if max_docs is None:
            max_docs = self.rerank_top_n

        query_terms = [term for term in query.lower().split() if term.strip()]

        def score(doc: Dict) -> int:
            text = doc.get("text", "").lower()
            metadata = doc.get("metadata", {})
            source = str(metadata.get("source", "")).lower()
            doc_type = str(metadata.get("doc_type", "")).lower()

            text_score = sum(term in text for term in query_terms)
            source_score = sum(term in source for term in query_terms)
            type_score = sum(term in doc_type for term in query_terms)

            return text_score + source_score + type_score

        ranked = sorted(docs, key=score, reverse=True)
        return ranked[:max_docs]

    def _build_context(self, docs: List[Dict]) -> str:
        """
        Build the final context block for the LLM.
        """
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
        """
        Inject retrieved context and user question into prompt template.
        """
        return self.prompt_template.format(
            context=context,
            question=question,
        )

    def _generate(self, prompt: str) -> str:
        """
        Call OpenAI chat completion.
        """
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
        """
        Full RAG execution pipeline.
        Always returns a consistent dictionary shape.
        """
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
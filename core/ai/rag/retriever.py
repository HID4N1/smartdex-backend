from typing import List, Dict, Optional
import chromadb
from django.conf import settings
from openai import OpenAI
import os
import logging
import re
import unicodedata


logger = logging.getLogger(__name__)


class Retriever:
    def __init__(
        self,
        collection_name: str = "smartdex_kb"
    ):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "missing-openai-api-key")

        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )

    def embed_query(self, text: str) -> List[float]:
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

    def search(
        self,
        query: str,
        top_k: int = 8,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        try:
            query_embedding = self.embed_query(query)

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=filter_metadata
            )
        except Exception as exc:
            logger.warning("Embedding search failed. Falling back to lexical search: %s", exc)
            return self._lexical_search(
                query=query,
                top_k=top_k,
                filter_metadata=filter_metadata,
            )

        return self._format_results(results)

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return " ".join(re.findall(r"[a-z0-9]+", text))

    def _lexical_search(
        self,
        query: str,
        top_k: int = 8,
        filter_metadata: Optional[Dict] = None,
    ) -> List[Dict]:
        results = self.collection.get(
            where=filter_metadata,
            include=["documents", "metadatas"],
        )

        documents = results.get("documents") or []
        metadatas = results.get("metadatas") or []
        ids = results.get("ids") or []

        query_terms = [
            term for term in self._normalize_text(query).split()
            if len(term) > 2
        ]

        if not query_terms:
            return []

        scored = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            haystack = self._normalize_text(
                " ".join([
                    text or "",
                    str(metadata.get("source", "")),
                    str(metadata.get("doc_type", "")),
                ])
            )

            score = sum(haystack.count(term) for term in query_terms)
            if score <= 0:
                continue

            scored.append({
                "id": ids[index] if index < len(ids) else str(index),
                "text": text,
                "metadata": metadata,
                "distance": 1 / score,
                "lexical_score": score,
            })

        scored.sort(key=lambda item: item["lexical_score"], reverse=True)
        return scored[:top_k]

    def _format_results(self, results: Dict) -> List[Dict]:
        formatted = []

        if not results or "documents" not in results:
            return formatted

        documents = results["documents"][0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        for i in range(len(documents)):
            formatted.append({
                "id": ids[i],
                "text": documents[i],
                "metadata": metadatas[i],
                "distance": distances[i] if i < len(distances) else None,
            })

        return formatted

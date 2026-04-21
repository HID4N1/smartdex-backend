from typing import List, Dict
import chromadb
from chromadb.config import Settings

from openai import OpenAI
import os


class Retriever:
    def __init__(
        self,
        persist_directory: str = "chroma_db",
        collection_name: str = "smartdex_kb"
    ):
        
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )


    def embed_query(self, text: str) -> List[float]:
        """
        Converts query into embedding vector.
        """

        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )

        return response.data[0].embedding

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Dict = None
    ) -> List[Dict]:
        """
        Performs semantic search on vector DB.
        """

        query_embedding = self.embed_query(query)

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filter_metadata  
        )

        return self._format_results(results)


    def _format_results(self, results: Dict) -> List[Dict]:
        """
        Converts ChromaDB output into clean RAG context format.
        """

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
                "score": distances[i] if i < len(distances) else None
            })

        return formatted
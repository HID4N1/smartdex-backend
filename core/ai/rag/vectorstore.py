import chromadb
from django.conf import settings

from core.ai.provider import AIOperationRunner, build_openai_client, create_embeddings

class VectorStore:
    """Explicit maintenance-only writer used by the ingestion script."""

    def __init__(self, allow_create=False, openai_client=None, ai_runner=None):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR
        )

        collection_loader = (
            self.client.get_or_create_collection
            if allow_create
            else self.client.get_collection
        )
        self.collection = collection_loader(name="smartdex_kb")

        self.openai_client = openai_client or build_openai_client()
        self.ai_runner = ai_runner or AIOperationRunner()

    def embed_texts(self, texts):
        embeddings = []
        batch_size = settings.OPENAI_EMBEDDING_BATCH_SIZE
        for start in range(0, len(texts), batch_size):
            embeddings.extend(
                create_embeddings(
                    client=self.openai_client,
                    runner=self.ai_runner,
                    operation="knowledge_base_embedding",
                    model=settings.OPENAI_EMBEDDING_MODEL,
                    inputs=texts[start:start + batch_size],
                )
            )
        return embeddings

    def add_documents(self, ids, texts, metadatas):
        embeddings = self.embed_texts(texts)

        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,  
            metadatas=metadatas
        )

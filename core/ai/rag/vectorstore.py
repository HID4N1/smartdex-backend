import chromadb
from django.conf import settings
from openai import OpenAI
import os

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_DIR
        )

        self.collection = self.client.get_or_create_collection(
            name="smartdex_kb"
        )

        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def embed_texts(self, texts):
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [d.embedding for d in response.data]

    def add_documents(self, ids, texts, metadatas):
        embeddings = self.embed_texts(texts)

        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,  
            metadatas=metadatas
        )

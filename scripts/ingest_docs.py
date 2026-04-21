# scripts/ingest_docs.py

import uuid
from core.ai.rag.loader import load_txt_files
from core.ai.rag.vectorstore import VectorStore
from core.utils.clean_text import clean_text
from core.utils.chunker import chunk_text
from core.utils.validators import is_valid_text
from dotenv import load_dotenv
load_dotenv()


DOCUMENTS_PATH = "static/documents"

def get_doc_type(filename: str) -> str:
    mapping = {
        "company_info.txt": "company",
        "faq.txt": "faq",
        "pricing_guide.txt": "pricing",
        "pricing_info.txt": "pricing",  # in case you used this name
        "services_detailed.txt": "services",
        "rules.txt": "rules",
        "technical_stack.txt": "technical",
        "knowledge_base.txt": "general",
    }
    return mapping.get(filename, "general")

def build_chunks(documents):
    """
    Converts raw documents into chunks with metadata.
    """

    chunks = []

    for filename, content in documents.items():

        if not is_valid_text(content):
            continue

        # 1. clean
        cleaned = clean_text(content)

        # 2. chunk
        split_chunks = chunk_text(cleaned)

        for i, chunk in enumerate(split_chunks):
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": chunk,
                "metadata": {
                    "source": filename,
                    "chunk_index": i,
                    "doc_type": get_doc_type(filename),
                }
            })

    return chunks


def ingest():
    print("Loading documents...")

    documents = load_txt_files(DOCUMENTS_PATH)

    print(f"Loaded {len(documents)} files")

    chunks = build_chunks(documents)

    print(f"Generated {len(chunks)} chunks")

    vectorstore = VectorStore()

    print("Storing embeddings...")

    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    vectorstore.add_documents(ids, texts, metadatas)

    print("Ingestion complete!")


if __name__ == "__main__":
    ingest()

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
        "pricing_info.txt": "pricing",
        "services_detailed.txt": "services",
        "rules.txt": "rules",
        "technical_stack.txt": "technical",
        "knowledge_base.txt": "general",
    }
    return mapping.get(filename, "general")


def get_chunking_config(doc_type: str) -> dict:
    configs = {
        "faq": {"chunk_size": 350, "overlap": 50},
        "rules": {"chunk_size": 300, "overlap": 40},
        "pricing": {"chunk_size": 500, "overlap": 80},
        "services": {"chunk_size": 600, "overlap": 100},
        "technical": {"chunk_size": 700, "overlap": 120},
        "company": {"chunk_size": 450, "overlap": 70},
        "general": {"chunk_size": 550, "overlap": 90},
    }
    return configs.get(doc_type, configs["general"])


def build_chunks(documents):
    chunks = []

    for filename, content in documents.items():
        if not is_valid_text(content):
            continue

        doc_type = get_doc_type(filename)
        cleaned = clean_text(content)
        chunking = get_chunking_config(doc_type)

        split_chunks = chunk_text(
            cleaned,
            chunk_size=chunking["chunk_size"],
            overlap=chunking["overlap"],
        )

        total_chunks = len(split_chunks)

        for i, chunk in enumerate(split_chunks):
            chunks.append({
                "id": str(uuid.uuid4()),
                "text": chunk,
                "metadata": {
                    "source": filename,
                    "chunk_index": i,
                    "total_chunks": total_chunks,
                    "doc_type": doc_type,
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
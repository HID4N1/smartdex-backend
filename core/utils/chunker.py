# core/utils/chunker.py
from typing import List

def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150
) -> List[str]:
    """
    Splits text into overlapping chunks for embeddings.
    Designed for RAG retrieval quality.
    """

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks
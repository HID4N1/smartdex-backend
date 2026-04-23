from typing import List


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150
) -> List[str]:
    """
    Splits text into overlapping chunks while trying to preserve
    paragraph and sentence boundaries for better RAG retrieval.
    """

    if not text or chunk_size <= 0:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    text = text.strip()
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        target_end = min(start + chunk_size, text_length)

        if target_end == text_length:
            chunk = text[start:target_end].strip()
            if chunk:
                chunks.append(chunk)
            break

        window = text[start:target_end]

        split_pos = max(
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind(". "),
            window.rfind("? "),
            window.rfind("! "),
        )

        if split_pos == -1 or split_pos < chunk_size // 2:
            split_pos = target_end - start
        else:
            split_pos += 1

        end = start + split_pos
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = max(end - overlap, start + 1)

    return chunks
import re

def clean_text(text: str) -> str:
    """
    Cleans raw text before chunking or embedding.
    Removes noise, normalizes spacing, and standardizes format.
    """

    if not text:
        return ""

    # Normalize line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Remove multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove weird non-printable characters
    text = re.sub(r"[^\x20-\x7E\n]", "", text)

    # Strip spaces
    text = text.strip()

    return text
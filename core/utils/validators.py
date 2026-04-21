import re

def is_valid_text(text: str) -> bool:
    """
    Checks if text is valid for processing.
    """

    if not text:
        return False

    if len(text.strip()) < 2:
        return False

    return True


def sanitize_query(query: str) -> str:
    """
    Sanitizes user input for retrieval / LLM queries.
    """

    if not query:
        return ""

    query = query.strip()

    # Remove excessive spaces
    query = re.sub(r"\s+", " ", query)

    # Optional: remove dangerous characters
    query = re.sub(r"[<>{}]", "", query)

    return query


def is_safe_filename(name: str) -> bool:
    """
    Prevents unsafe file access patterns.
    """

    return bool(re.match(r"^[a-zA-Z0-9_\-\.]+$", name))
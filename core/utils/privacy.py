from __future__ import annotations

import re
from typing import Any, Iterable


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&\s]+", re.IGNORECASE)
ADDRESS_LABEL_RE = re.compile(
    r"\b(address|adresse)\s*(?:is|est|:)?\s*[^.\n]+",
    re.IGNORECASE,
)

SENSITIVE_KEY_PARTS = {
    "access_token",
    "token",
    "client_name",
    "client_email",
    "client_phone",
    "email",
    "phone",
    "address",
    "adresse",
    "street",
    "city",
    "postal",
    "zip",
    "contact",
}


def redact_pii_text(text: str | None, known_sensitive_values: Iterable[str | None] = ()) -> str:
    if not text:
        return ""

    redacted = str(text)
    redacted = TOKEN_QUERY_RE.sub(r"\1[REDACTED_TOKEN]", redacted)
    redacted = ADDRESS_LABEL_RE.sub(r"\1 [REDACTED_ADDRESS]", redacted)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = UUID_RE.sub("[REDACTED_TOKEN]", redacted)

    for value in known_sensitive_values:
        if not value:
            continue
        value_text = str(value).strip()
        if len(value_text) < 2:
            continue
        redacted = re.sub(re.escape(value_text), "[REDACTED_CLIENT]", redacted, flags=re.IGNORECASE)

    return redacted


def is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def redact_for_ai(value: Any, known_sensitive_values: Iterable[str | None] = ()) -> Any:
    if isinstance(value, str):
        return redact_pii_text(value, known_sensitive_values)
    if isinstance(value, list):
        return [redact_for_ai(item, known_sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [redact_for_ai(item, known_sensitive_values) for item in value]
    if isinstance(value, dict):
        return {
            key: redact_for_ai(item, known_sensitive_values)
            for key, item in value.items()
            if not is_sensitive_key(str(key))
        }
    return value

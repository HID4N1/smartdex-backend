from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
OPENAI_API_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
BEARER_TOKEN_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
AUTH_HEADER_RE = re.compile(
    r"\b(authorization|cookie|set-cookie)\s*[:=]\s*[^;\n\r]+",
    re.IGNORECASE,
)
DATABASE_URL_RE = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|redis)://[^\s'\"<>]+",
    re.IGNORECASE,
)
TOKEN_QUERY_RE = re.compile(
    r"([?&](?:token|access_token|key|api_key)=)[^&\s]+",
    re.IGNORECASE,
)
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
    "authorization",
    "cookie",
    "sessionid",
    "secret",
    "api_key",
    "database_url",
    "password",
}

SENSITIVE_QUERY_KEYS = {"token", "access_token", "key", "api_key"}


def redact_url_query(url: str | None) -> str:
    if not url:
        return ""

    parts = urlsplit(str(url))
    if not parts.query:
        return str(url)

    redacted_query = urlencode(
        [
            (key, "[REDACTED_TOKEN]" if key.lower() in SENSITIVE_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted_query, parts.fragment))


def redact_pii_text(text: str | None, known_sensitive_values: Iterable[str | None] = ()) -> str:
    if not text:
        return ""

    redacted = str(text)
    redacted = TOKEN_QUERY_RE.sub(r"\1[REDACTED_TOKEN]", redacted)
    redacted = OPENAI_API_KEY_RE.sub("[REDACTED_API_KEY]", redacted)
    redacted = BEARER_TOKEN_RE.sub("Bearer [REDACTED_TOKEN]", redacted)
    redacted = AUTH_HEADER_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", redacted)
    redacted = DATABASE_URL_RE.sub("[REDACTED_DATABASE_URL]", redacted)
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


def sanitize_for_log(value: Any, known_sensitive_values: Iterable[str | None] = ()) -> Any:
    if isinstance(value, str):
        return redact_pii_text(value, known_sensitive_values)
    if isinstance(value, list):
        return [sanitize_for_log(item, known_sensitive_values) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_log(item, known_sensitive_values) for item in value)
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED_SECRET]"
                if is_sensitive_key(str(key))
                else sanitize_for_log(item, known_sensitive_values)
            )
            for key, item in value.items()
        }
    return value


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

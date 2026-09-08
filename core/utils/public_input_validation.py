import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from rest_framework import serializers


PUBLIC_JSON_BODY_LIMIT_BYTES = 2 * 1024 * 1024

SHORT_TEXT_LIMITS = {
    "contact_name": 100,
    "contact_company": 150,
    "contact_subject": 200,
    "contact_project_type": 50,
    "contact_budget": 50,
    "devis_client_name": 150,
    "devis_client_phone": 30,
    "devis_project_type": 100,
    "devis_budget_range": 100,
    "devis_timeline": 100,
    "devis_preferred_language": 10,
}

CONTACT_MESSAGE_MAX_LENGTH = 2000
DEVIS_DESCRIPTION_MAX_LENGTH = 10000
CHAT_MESSAGE_MAX_LENGTH = 4000
CHAT_HISTORY_MAX_MESSAGES = 30
CHAT_HISTORY_MAX_CHARACTERS = 30000
DEVIS_CHAT_MESSAGES_MAX_ITEMS = 30
DEVIS_FEATURES_MAX_ITEMS = 30
DEVIS_FEATURE_MAX_LENGTH = 200
DEVIS_EXTRA_HINTS_MAX_KEYS = 20
DEVIS_EXTRA_HINT_KEY_MAX_LENGTH = 100
DEVIS_EXTRA_HINT_STRING_MAX_LENGTH = 500
DEVIS_EXTRA_HINT_LIST_MAX_ITEMS = 10
DEVIS_BUDGET_MAX_VALUE = Decimal("10000000")

PHONE_RE = re.compile(r"^[\d\s+\-().]+$")
NEGATIVE_MONEY_RE = re.compile(r"(^|\s)-\s*\d")
MONEY_TOKEN_RE = re.compile(r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<suffix>[kKmM])?")


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def has_disallowed_control_characters(value: str, *, allow_multiline: bool = False) -> bool:
    allowed = {"\n", "\r", "\t"} if allow_multiline else set()
    return any(
        char not in allowed and unicodedata.category(char).startswith("C")
        for char in value
    )


def validate_short_text(value: str, *, field_name: str, max_length: int, allow_blank: bool = False) -> str:
    normalized = normalize_text(value or "")
    if not normalized:
        if allow_blank:
            return ""
        raise serializers.ValidationError("This field may not be blank.")
    if len(normalized) > max_length:
        raise serializers.ValidationError(f"Ensure this field has no more than {max_length} characters.")
    if has_disallowed_control_characters(normalized):
        raise serializers.ValidationError(f"{field_name} contains unsupported control characters.")
    return normalized


def validate_long_text(value: str, *, max_length: int, min_meaningful_length: int = 1) -> str:
    normalized = (value or "").strip()
    if len(normalized) < min_meaningful_length:
        raise serializers.ValidationError("This field must contain meaningful text.")
    if len(normalized) > max_length:
        raise serializers.ValidationError(f"Ensure this field has no more than {max_length} characters.")
    if has_disallowed_control_characters(normalized, allow_multiline=True):
        raise serializers.ValidationError("This field contains unsupported control characters.")
    return normalized


def validate_phone(value: str, *, allow_blank: bool = True) -> str:
    normalized = validate_short_text(
        value,
        field_name="Phone",
        max_length=SHORT_TEXT_LIMITS["devis_client_phone"],
        allow_blank=allow_blank,
    )
    if normalized and not PHONE_RE.fullmatch(normalized):
        raise serializers.ValidationError("Enter a valid phone number.")
    return normalized


def validate_features(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError("Features must be a list.")
    if len(value) > DEVIS_FEATURES_MAX_ITEMS:
        raise serializers.ValidationError(f"Provide no more than {DEVIS_FEATURES_MAX_ITEMS} features.")

    features = []
    for item in value:
        if not isinstance(item, str):
            raise serializers.ValidationError("Each feature must be a string.")
        features.append(
            validate_short_text(
                item,
                field_name="Feature",
                max_length=DEVIS_FEATURE_MAX_LENGTH,
            )
        )
    return features


def _validate_extra_hint_scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if len(normalized) > DEVIS_EXTRA_HINT_STRING_MAX_LENGTH:
            raise serializers.ValidationError(
                f"Extra hint values must be no more than {DEVIS_EXTRA_HINT_STRING_MAX_LENGTH} characters."
            )
        if has_disallowed_control_characters(normalized, allow_multiline=True):
            raise serializers.ValidationError("Extra hint values contain unsupported control characters.")
        return normalized
    raise serializers.ValidationError("Extra hint values must be strings, numbers, booleans, null, or flat lists.")


def validate_extra_hints(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Extra hints must be an object.")
    if len(value) > DEVIS_EXTRA_HINTS_MAX_KEYS:
        raise serializers.ValidationError(f"Provide no more than {DEVIS_EXTRA_HINTS_MAX_KEYS} extra hints.")

    cleaned = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            raise serializers.ValidationError("Extra hint keys must be strings.")
        clean_key = validate_short_text(
            key,
            field_name="Extra hint key",
            max_length=DEVIS_EXTRA_HINT_KEY_MAX_LENGTH,
        )
        if isinstance(raw_value, list):
            if len(raw_value) > DEVIS_EXTRA_HINT_LIST_MAX_ITEMS:
                raise serializers.ValidationError(
                    f"Extra hint lists must contain no more than {DEVIS_EXTRA_HINT_LIST_MAX_ITEMS} items."
                )
            cleaned[clean_key] = [_validate_extra_hint_scalar(item) for item in raw_value]
        elif isinstance(raw_value, dict):
            raise serializers.ValidationError("Nested extra hint objects are not supported.")
        else:
            cleaned[clean_key] = _validate_extra_hint_scalar(raw_value)
    return cleaned


def validate_budget_text(value: str) -> str:
    normalized = validate_short_text(
        value,
        field_name="Budget",
        max_length=SHORT_TEXT_LIMITS["devis_budget_range"],
        allow_blank=True,
    )
    if NEGATIVE_MONEY_RE.search(normalized):
        raise serializers.ValidationError("Budget values cannot be negative.")
    for match in MONEY_TOKEN_RE.finditer(normalized):
        try:
            amount = Decimal(match.group("amount").replace(",", "."))
        except InvalidOperation:
            continue
        suffix = (match.group("suffix") or "").lower()
        if suffix == "k":
            amount *= Decimal("1000")
        elif suffix == "m":
            amount *= Decimal("1000000")
        if amount > DEVIS_BUDGET_MAX_VALUE:
            raise serializers.ValidationError("Budget value is unrealistically large.")
    return normalized


def aggregate_message_characters(messages: list[dict[str, Any]], *, include: str = "") -> int:
    return sum(len(message.get("content") or "") for message in messages) + len(include)

from rest_framework import serializers

from apps.contact.models import ContactMessage
from core.utils.public_input_validation import (
    CONTACT_MESSAGE_MAX_LENGTH,
    SHORT_TEXT_LIMITS,
    validate_long_text,
    validate_short_text,
)


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = (
            "name",
            "email",
            "company",
            "project_type",
            "budget",
            "subject",
            "message",
        )
        extra_kwargs = {
            "name": {"max_length": SHORT_TEXT_LIMITS["contact_name"], "trim_whitespace": True},
            "email": {"max_length": 254, "trim_whitespace": True},
            "company": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["contact_company"],
                "trim_whitespace": True,
            },
            "project_type": {"required": False, "allow_blank": True},
            "budget": {"required": False, "allow_blank": True},
            "subject": {"max_length": SHORT_TEXT_LIMITS["contact_subject"], "trim_whitespace": True},
            "message": {
                "max_length": CONTACT_MESSAGE_MAX_LENGTH,
                "trim_whitespace": True,
                "style": {"base_template": "textarea.html"},
            },
        }

    def validate_name(self, value):
        return validate_short_text(
            value,
            field_name="Name",
            max_length=SHORT_TEXT_LIMITS["contact_name"],
        )

    def validate_company(self, value):
        return validate_short_text(
            value,
            field_name="Company",
            max_length=SHORT_TEXT_LIMITS["contact_company"],
            allow_blank=True,
        )

    def validate_subject(self, value):
        return validate_short_text(
            value,
            field_name="Subject",
            max_length=SHORT_TEXT_LIMITS["contact_subject"],
        )

    def validate_budget(self, value):
        return validate_short_text(
            value,
            field_name="Budget",
            max_length=SHORT_TEXT_LIMITS["contact_budget"],
            allow_blank=True,
        )

    def validate_message(self, value):
        normalized = validate_long_text(
            value,
            max_length=CONTACT_MESSAGE_MAX_LENGTH,
            min_meaningful_length=1,
        )
        if len(normalized) < 20:
            raise serializers.ValidationError(
                "Message must be at least 20 characters long."
            )
        return normalized

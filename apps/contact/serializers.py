from rest_framework import serializers

from apps.contact.models import ContactMessage


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
            "name": {"max_length": 150, "trim_whitespace": True},
            "email": {"max_length": 254, "trim_whitespace": True},
            "company": {
                "required": False,
                "allow_blank": True,
                "max_length": 150,
                "trim_whitespace": True,
            },
            "project_type": {"required": False, "allow_blank": True},
            "budget": {"required": False, "allow_blank": True},
            "subject": {"max_length": 200, "trim_whitespace": True},
            "message": {
                "max_length": 2000,
                "trim_whitespace": True,
                "style": {"base_template": "textarea.html"},
            },
        }

    def validate_message(self, value):
        if len(value.strip()) < 20:
            raise serializers.ValidationError(
                "Message must be at least 20 characters long."
            )
        return value

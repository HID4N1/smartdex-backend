from rest_framework import serializers
from apps.devis.models import DevisRequest
from core.utils.public_input_validation import (
    CHAT_HISTORY_MAX_CHARACTERS,
    CHAT_MESSAGE_MAX_LENGTH,
    DEVIS_CHAT_MESSAGES_MAX_ITEMS,
    DEVIS_DESCRIPTION_MAX_LENGTH,
    SHORT_TEXT_LIMITS,
    aggregate_message_characters,
    validate_budget_text,
    validate_extra_hints,
    validate_features,
    validate_long_text,
    validate_phone,
    validate_short_text,
)


class DevisRequestCreateSerializer(serializers.ModelSerializer):
    features = serializers.JSONField(required=False)
    extra_hints = serializers.JSONField(required=False)

    class Meta:
        model = DevisRequest
        fields = [
            "id",
            "description",
            "client_name",
            "client_email",
            "client_phone",
            "budget_range",
            "timeline",
            "project_type",
            "preferred_language",
            "features",
            "extra_hints",
            "marketing_consent",
            "access_token",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "access_token", "status", "created_at", "updated_at"]
        extra_kwargs = {
            "description": {"max_length": DEVIS_DESCRIPTION_MAX_LENGTH, "trim_whitespace": True},
            "client_name": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_client_name"],
                "trim_whitespace": True,
            },
            "client_email": {"required": False, "allow_blank": True, "max_length": 254, "trim_whitespace": True},
            "client_phone": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_client_phone"],
                "trim_whitespace": True,
            },
            "budget_range": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_budget_range"],
                "trim_whitespace": True,
            },
            "timeline": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_timeline"],
                "trim_whitespace": True,
            },
            "project_type": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_project_type"],
                "trim_whitespace": True,
            },
            "preferred_language": {
                "required": False,
                "allow_blank": True,
                "max_length": SHORT_TEXT_LIMITS["devis_preferred_language"],
                "trim_whitespace": True,
            },
            "marketing_consent": {"required": False},
        }

    def validate_description(self, value):
        return validate_long_text(value, max_length=DEVIS_DESCRIPTION_MAX_LENGTH)

    def validate_client_name(self, value):
        return validate_short_text(
            value,
            field_name="Client name",
            max_length=SHORT_TEXT_LIMITS["devis_client_name"],
            allow_blank=True,
        )

    def validate_client_phone(self, value):
        return validate_phone(value)

    def validate_budget_range(self, value):
        return validate_budget_text(value)

    def validate_timeline(self, value):
        return validate_short_text(
            value,
            field_name="Timeline",
            max_length=SHORT_TEXT_LIMITS["devis_timeline"],
            allow_blank=True,
        )

    def validate_project_type(self, value):
        return validate_short_text(
            value,
            field_name="Project type",
            max_length=SHORT_TEXT_LIMITS["devis_project_type"],
            allow_blank=True,
        )

    def validate_preferred_language(self, value):
        return validate_short_text(
            value,
            field_name="Preferred language",
            max_length=SHORT_TEXT_LIMITS["devis_preferred_language"],
            allow_blank=True,
        )

    def validate_features(self, value):
        return validate_features(value)

    def validate_extra_hints(self, value):
        return validate_extra_hints(value)


class QuoteItemSerializer(serializers.Serializer):
    key = serializers.CharField(allow_null=True, required=False)
    label = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    price_min = serializers.IntegerField()
    price_max = serializers.IntegerField()


class IncludedGroupSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    items = QuoteItemSerializer(many=True)


class TotalsSerializer(serializers.Serializer):
    included_min = serializers.IntegerField()
    included_max = serializers.IntegerField()
    optional_min = serializers.IntegerField()
    optional_max = serializers.IntegerField()
    recurring_min = serializers.IntegerField()
    recurring_max = serializers.IntegerField()
    grand_total_min = serializers.IntegerField()
    grand_total_max = serializers.IntegerField()


class EstimateSerializer(serializers.Serializer):
    range_min = serializers.IntegerField()
    range_max = serializers.IntegerField()
    currency = serializers.CharField()
    cost_drivers = serializers.ListField(child=serializers.CharField())
    recommendation = serializers.CharField()


class QuoteSerializer(serializers.Serializer):
    included_groups = IncludedGroupSerializer(many=True)
    optional_items = QuoteItemSerializer(many=True)
    recurring_items = serializers.ListField(
        child=QuoteItemSerializer(),
        required=False,
        default=list,
    )
    totals = TotalsSerializer()
    notes = serializers.ListField(child=serializers.CharField())
    missing_information = serializers.ListField(child=serializers.CharField())


class ChatContextMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(
        max_length=CHAT_MESSAGE_MAX_LENGTH,
        trim_whitespace=True,
    )

    def validate_content(self, value):
        return validate_long_text(value, max_length=CHAT_MESSAGE_MAX_LENGTH)


class GenerateDevisFromChatSerializer(serializers.Serializer):
    messages = ChatContextMessageSerializer(
        many=True,
        required=False,
        max_length=DEVIS_CHAT_MESSAGES_MAX_ITEMS,
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=DEVIS_DESCRIPTION_MAX_LENGTH,
        trim_whitespace=True,
    )
    client_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=SHORT_TEXT_LIMITS["devis_client_name"],
        trim_whitespace=True,
    )
    client_email = serializers.EmailField(required=False, allow_blank=True)
    client_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=SHORT_TEXT_LIMITS["devis_client_phone"],
        trim_whitespace=True,
    )
    preferred_language = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=SHORT_TEXT_LIMITS["devis_preferred_language"],
        trim_whitespace=True,
    )

    def validate_description(self, value):
        if not value:
            return ""
        return validate_long_text(value, max_length=DEVIS_DESCRIPTION_MAX_LENGTH)

    def validate_client_name(self, value):
        return validate_short_text(
            value,
            field_name="Client name",
            max_length=SHORT_TEXT_LIMITS["devis_client_name"],
            allow_blank=True,
        )

    def validate_client_phone(self, value):
        return validate_phone(value)

    def validate_preferred_language(self, value):
        return validate_short_text(
            value,
            field_name="Preferred language",
            max_length=SHORT_TEXT_LIMITS["devis_preferred_language"],
            allow_blank=True,
        )

    def validate(self, attrs):
        messages = attrs.get("messages") or []
        description = (attrs.get("description") or "").strip()
        if aggregate_message_characters(messages, include=description) > CHAT_HISTORY_MAX_CHARACTERS:
            raise serializers.ValidationError(
                f"Chat context must contain no more than {CHAT_HISTORY_MAX_CHARACTERS} characters."
            )
        if not messages and not description:
            raise serializers.ValidationError(
                "At least one of messages or description is required."
            )
        if messages and not description and not any(
            message["role"] == "user" and message["content"].strip()
            for message in messages
        ):
            raise serializers.ValidationError("At least one user message with content is required.")
        return attrs


class GeneratedQuoteResponseSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()
    access_token = serializers.UUIDField(required=False)
    status = serializers.CharField()
    estimate = EstimateSerializer()
    quote = QuoteSerializer()
    pdf_url = serializers.CharField(required=False, allow_null=True)
    clarification_questions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    selected_features = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

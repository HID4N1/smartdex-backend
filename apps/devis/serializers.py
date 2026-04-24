from rest_framework import serializers
from apps.devis.models import DevisRequest


class DevisRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevisRequest
        fields = "__all__"


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
    role = serializers.CharField()
    content = serializers.CharField()


class GenerateDevisFromChatSerializer(serializers.Serializer):
    messages = ChatContextMessageSerializer(many=True, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    client_name = serializers.CharField(required=False, allow_blank=True)
    client_email = serializers.EmailField(required=False, allow_blank=True)
    client_phone = serializers.CharField(required=False, allow_blank=True)
    preferred_language = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        messages = attrs.get("messages") or []
        description = (attrs.get("description") or "").strip()
        if not messages and not description:
            raise serializers.ValidationError(
                "At least one of messages or description is required."
            )
        return attrs


class GeneratedQuoteResponseSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()
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

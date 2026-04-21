from rest_framework import serializers
from apps.devis.models import DevisRequest


class DevisRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevisRequest
        fields = "__all__"


class QuoteItemSerializer(serializers.Serializer):
    key = serializers.CharField()
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


class GeneratedQuoteResponseSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()
    status = serializers.CharField()
    estimate = EstimateSerializer()
    quote = QuoteSerializer()
from rest_framework import serializers
from .models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = (
            'id', 'company', 'plan', 'billing_type', 'price_per_unit', 'interval',
            'students_count', 'amount_billed', 'started_at', 'expires_at', 'status',
        )
        read_only_fields = fields

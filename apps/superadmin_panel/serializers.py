from rest_framework import serializers
from .models import SuperadminLog
from apps.companies.models import Company
from apps.subscriptions.models import Subscription


class SuperadminLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = SuperadminLog
        fields = ('id', 'user', 'user_name', 'action', 'description', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')


class SuperadminLogCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuperadminLog
        fields = ('id', 'action', 'description')
        read_only_fields = ('id',)


class CompanyWithSubscriptionSerializer(serializers.ModelSerializer):
    active_subscription = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()
    branch_of_name = serializers.CharField(source='branch_of.name', read_only=True)

    class Meta:
        model = Company
        fields = ('id', 'name', 'phone', 'address', 'status', 'branch_of', 'branch_of_name', 'created_at', 'active_subscription', 'user_count')

    def get_active_subscription(self, obj):
        sub = obj.subscriptions.filter(status='active').first()
        if not sub:
            return None
        return {'plan': sub.plan, 'expires_at': sub.expires_at, 'status': sub.status}

    def get_user_count(self, obj):
        return obj.users.filter(status='active').count()

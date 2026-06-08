from rest_framework import serializers
from .models import SuperadminLog, SubscriptionPlan, CompanySubscriptionDebt, CompanySubscriptionPayment
from apps.companies.models import Company


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


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ('id', 'price', 'updated_at', 'updated_by')
        read_only_fields = ('id', 'updated_at', 'updated_by')


class CompanySubscriptionDebtSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_id = serializers.UUIDField(source='company.id', read_only=True)
    paid_amount = serializers.SerializerMethodField()

    class Meta:
        model = CompanySubscriptionDebt
        fields = ('id', 'company_id', 'company_name', 'amount', 'paid_amount',
                  'period_start', 'period_end', 'status', 'created_at')

    def get_paid_amount(self, obj):
        from decimal import Decimal
        from django.db.models import Sum
        total = obj.payments.aggregate(t=Sum('amount'))['t']
        return total or Decimal('0')


class CompanySubscriptionPaymentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    period_start = serializers.DateField(source='debt.period_start', read_only=True)
    period_end = serializers.DateField(source='debt.period_end', read_only=True)

    class Meta:
        model = CompanySubscriptionPayment
        fields = ('id', 'company_name', 'amount', 'paid_at', 'recorded_by_name',
                  'period_start', 'period_end')


class CompanyCardSerializer(serializers.ModelSerializer):
    branch_of_name = serializers.CharField(source='branch_of.name', read_only=True)
    is_branch = serializers.SerializerMethodField()
    active_student_count = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    branches = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'phone', 'address', 'status',
            'branch_of', 'branch_of_name', 'is_branch',
            'active_student_count', 'subscription_status',
            'branches', 'created_at',
        )

    def get_is_branch(self, obj):
        return obj.branch_of_id is not None

    def get_active_student_count(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj, status='active').count()

    def get_subscription_status(self, obj):
        debt = obj.subscription_debts.order_by('-created_at').first()
        return debt.status if debt else None

    def get_branches(self, obj):
        return [{'id': str(b.id), 'name': b.name} for b in obj.branches.filter(status='active')]


# Keep backwards-compat alias used by existing views
class CompanyWithSubscriptionSerializer(serializers.ModelSerializer):
    active_subscription = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()
    branch_of_name = serializers.CharField(source='branch_of.name', read_only=True)

    class Meta:
        model = Company
        fields = ('id', 'name', 'phone', 'address', 'status', 'branch_of',
                  'branch_of_name', 'created_at', 'active_subscription', 'user_count')

    def get_active_subscription(self, obj):
        try:
            from apps.subscriptions.models import Subscription
            sub = obj.subscriptions.filter(status='active').first()
            if not sub:
                return None
            return {'plan': sub.plan, 'expires_at': sub.expires_at, 'status': sub.status}
        except Exception:
            return None

    def get_user_count(self, obj):
        return obj.users.filter(status='active').count()

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
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = CompanySubscriptionDebt
        fields = (
            'id', 'company_id', 'company_name', 'created_at',
            'amount', 'paid_amount', 'remaining',
            'period_start', 'period_end', 'status',
        )

    def get_paid_amount(self, obj):
        from decimal import Decimal
        from django.db.models import Sum
        total = obj.payments.aggregate(t=Sum('amount'))['t']
        return total or Decimal('0')

    def get_remaining(self, obj):
        from decimal import Decimal
        from django.db.models import Sum
        total = obj.payments.aggregate(t=Sum('amount'))['t']
        paid = total or Decimal('0')
        return obj.amount - paid

    def validate_amount(self, value):
        from decimal import Decimal
        if value < Decimal('10000'):
            raise serializers.ValidationError("Qarz miqdori 10,000 so'mdan kam bo'lishi mumkin emas.")
        plan = SubscriptionPlan.objects.first()
        if plan and value > plan.price:
            raise serializers.ValidationError(f"Qarz miqdori {plan.price} so'mdan oshmasligi mumkin emas.")
        return value


class CompanySubscriptionPaymentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_phone = serializers.CharField(source='company.phone', read_only=True)

    class Meta:
        model = CompanySubscriptionPayment
        fields = ('id', 'company_name', 'company_phone', 'amount', 'payment_method', 'paid_at')


class CompanyCardSerializer(serializers.ModelSerializer):
    branch_of_name = serializers.CharField(source='branch_of.name', read_only=True)
    is_branch = serializers.SerializerMethodField()
    active_student_count = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    branches = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'phone', 'address', 'status', 'logo',
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


class CompanyDetailSerializer(CompanyCardSerializer):
    total_students = serializers.SerializerMethodField()
    active_students = serializers.SerializerMethodField()
    trial_students = serializers.SerializerMethodField()
    frozen_students = serializers.SerializerMethodField()
    pending_students = serializers.SerializerMethodField()
    rejected_students = serializers.SerializerMethodField()
    archived_students = serializers.SerializerMethodField()

    class Meta(CompanyCardSerializer.Meta):
        fields = CompanyCardSerializer.Meta.fields + (
            'total_students', 'active_students', 'trial_students',
            'frozen_students', 'pending_students', 'rejected_students',
            'archived_students',
        )

    def get_total_students(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj).count()

    def get_active_students(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj, status='active').count()

    def get_trial_students(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj, status='trial').count()

    def get_frozen_students(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj, status='frozen').count()

    def get_pending_students(self, obj):
        from apps.leads.models import Lead
        return Lead.objects.filter(company=obj, status='pending').count()

    def get_rejected_students(self, obj):
        from apps.leads.models import Lead
        return Lead.objects.filter(company=obj, status='ignored').count()

    def get_archived_students(self, obj):
        from apps.students.models import Student
        return Student.objects.filter(company=obj, status='archived').count()

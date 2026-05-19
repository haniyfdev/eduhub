from rest_framework import serializers
from .models import TeacherSalary, StaffSalary, TeacherWorkLog, StaffKpiRule


class TeacherSalarySerializer(serializers.ModelSerializer):
    teacher_name    = serializers.CharField(source='teacher.user.get_full_name', read_only=True)
    teacher_subject = serializers.CharField(source='teacher.subject', read_only=True)
    salary_type       = serializers.CharField(source='teacher.salary_type', read_only=True)
    salary_percent    = serializers.DecimalField(source='teacher.salary_percent', max_digits=5, decimal_places=2, read_only=True)
    fixed_amount      = serializers.DecimalField(source='teacher.fixed_amount', max_digits=15, decimal_places=2, read_only=True)
    per_student_amt   = serializers.DecimalField(source='teacher.per_student_amt', max_digits=15, decimal_places=2, read_only=True)
    students_count    = serializers.SerializerMethodField()
    total_owed      = serializers.SerializerMethodField()
    carry_over      = serializers.SerializerMethodField()

    class Meta:
        model = TeacherSalary
        fields = (
            'id', 'company', 'teacher', 'teacher_name', 'teacher_subject',
            'salary_type', 'salary_percent', 'fixed_amount', 'per_student_amt', 'students_count', 'month',
            'base_amount', 'kpi_amount', 'total_amount',
            'calculated_amount', 'paid_amount', 'carry_over', 'total_owed',
            'status', 'is_paid', 'paid_at', 'note', 'created_at',
        )
        read_only_fields = ('id', 'company', 'created_at')

    def get_students_count(self, obj):
        from apps.groups.models import GroupStudent
        return GroupStudent.objects.filter(
            group__teacher=obj.teacher,
            group__status='active',
            left_at__isnull=True,
            student__status='active',
        ).count()

    def get_total_owed(self, obj):
        return obj.calculated_amount + self.get_carry_over(obj)

    def get_carry_over(self, obj):
        from django.db.models import Sum
        from decimal import Decimal
        result = TeacherSalary.objects.filter(
            teacher=obj.teacher,
            month__lt=obj.month,
            company=obj.company,
        ).exclude(status='paid').aggregate(
            total_calc=Sum('calculated_amount'),
            total_paid=Sum('paid_amount'),
        )
        total = (result['total_calc'] or Decimal('0')) - (result['total_paid'] or Decimal('0'))
        return max(total, Decimal('0'))


class StaffSalarySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = StaffSalary
        fields = (
            'id', 'company', 'user', 'user_name', 'month',
            'amount', 'kpi_amount', 'paid_at', 'note', 'created_at',
        )
        read_only_fields = ('id', 'company', 'created_at')


class StaffSalaryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffSalary
        fields = ('id', 'user', 'month', 'amount', 'kpi_amount', 'note')
        read_only_fields = ('id',)


class StaffKpiRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffKpiRule
        fields = (
            'id', 'company', 'name', 'role', 'metric',
            'threshold', 'bonus_amount', 'status', 'archived_at', 'created_at',
        )
        read_only_fields = ('id', 'company', 'archived_at', 'created_at')


class StaffKpiRuleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffKpiRule
        fields = ('id', 'name', 'role', 'metric', 'threshold', 'bonus_amount')
        read_only_fields = ('id',)


class TeacherWorkLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherWorkLog
        fields = ('id', 'company', 'teacher', 'lesson', 'hours', 'students_count', 'logged_at')
        read_only_fields = fields

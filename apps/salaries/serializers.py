from rest_framework import serializers
from .models import TeacherSalary, StaffSalary, TeacherWorkLog, StaffKpiRule


class TeacherSalarySerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True)

    class Meta:
        model = TeacherSalary
        fields = (
            'id', 'company', 'teacher', 'teacher_name', 'month',
            'base_amount', 'kpi_amount', 'total_amount', 'paid_at', 'note', 'created_at',
        )
        read_only_fields = ('id', 'company', 'created_at')


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

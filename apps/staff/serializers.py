from rest_framework import serializers
from .models import Staff, StaffSalary


class StaffSerializer(serializers.ModelSerializer):
    full_name    = serializers.CharField(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model  = Staff
        fields = (
            'id', 'company', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_display',
            'salary_amount', 'status', 'hired_at', 'notes',
        )
        read_only_fields = ('id', 'company', 'hired_at')


class StaffCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Staff
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'role',
            'salary_amount', 'notes',
        )
        read_only_fields = ('id',)


class StaffSalarySerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.full_name', read_only=True)
    staff_role = serializers.CharField(source='staff.get_role_display', read_only=True)
    hired_at   = serializers.CharField(source='staff.hired_at', read_only=True)
    total_owed = serializers.SerializerMethodField()

    class Meta:
        model  = StaffSalary
        fields = (
            'id', 'staff', 'staff_name', 'staff_role', 'hired_at', 'company', 'month',
            'calculated_amount', 'paid_amount', 'carry_over', 'total_owed',
            'due_date', 'status', 'is_paid', 'paid_at', 'note',
        )
        read_only_fields = ('id', 'company')

    def get_total_owed(self, obj):
        return obj.calculated_amount + obj.carry_over - obj.paid_amount

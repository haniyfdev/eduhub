from rest_framework import serializers
from .models import Staff, StaffSalary

ROLE_LABELS = {
    'admin':      'Admin',
    'manager':    'Menejer',
    'accountant': 'Buxgalter',
    'security':   'Qorovul',
    'cleaner':    'Farrosh',
    'supply':     'Zavxoz',
    'other':      'Boshqa',
}


class StaffSerializer(serializers.ModelSerializer):
    first_name   = serializers.CharField(source='user.first_name', read_only=True)
    last_name    = serializers.CharField(source='user.last_name', read_only=True)
    full_name    = serializers.CharField(source='user.get_full_name', read_only=True)
    phone        = serializers.CharField(source='user.phone', read_only=True)
    role         = serializers.CharField(source='user.role', read_only=True)
    role_display = serializers.SerializerMethodField()
    hired_at     = serializers.DateTimeField(source='user.created_at', read_only=True)

    class Meta:
        model  = Staff
        fields = (
            'id', 'user', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_display',
            'salary_amount', 'notes', 'status', 'hired_at',
        )
        read_only_fields = ('id', 'user')

    def get_role_display(self, obj):
        return ROLE_LABELS.get(obj.user.role, obj.user.role)


class StaffSalarySerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_role = serializers.SerializerMethodField()
    total_owed = serializers.SerializerMethodField()
    hired_at   = serializers.SerializerMethodField()

    class Meta:
        model  = StaffSalary
        fields = (
            'id', 'staff', 'staff_name', 'staff_role', 'hired_at', 'company', 'month',
            'calculated_amount', 'paid_amount', 'carry_over', 'total_owed',
            'due_date', 'status', 'is_paid', 'paid_at', 'note',
        )
        read_only_fields = ('id', 'company')

    def get_hired_at(self, obj):
        try:
            created_at = obj.staff.user.created_at
            if created_at:
                return created_at.strftime('%d/%m/%Y')
        except Exception:
            pass
        return None

    def get_staff_name(self, obj):
        return obj.staff.user.get_full_name()

    def get_staff_role(self, obj):
        return ROLE_LABELS.get(obj.staff.user.role, obj.staff.user.role)

    def get_total_owed(self, obj):
        return obj.calculated_amount + obj.carry_over - obj.paid_amount

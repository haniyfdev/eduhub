from rest_framework import serializers
from .models import Staff, StaffSalary


class StaffSerializer(serializers.ModelSerializer):
    full_name         = serializers.CharField(read_only=True)
    role_display      = serializers.CharField(source='get_role_display', read_only=True)
    contract_display  = serializers.CharField(source='get_contract_type_display', read_only=True)

    class Meta:
        model  = Staff
        fields = (
            'id', 'company', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'role_display', 'contract_type', 'contract_display',
            'salary_amount', 'contract_months', 'contract_start', 'contract_end',
            'status', 'hired_at', 'notes',
        )
        read_only_fields = ('id', 'company', 'hired_at', 'contract_end')


class StaffCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Staff
        fields = (
            'id', 'first_name', 'last_name', 'phone', 'role',
            'contract_type', 'salary_amount', 'contract_months', 'contract_start', 'notes',
        )
        read_only_fields = ('id',)

    def validate(self, data):
        if data.get('contract_type') == 'contract':
            if not data.get('contract_months'):
                raise serializers.ValidationError({'contract_months': "Shartnoma muddatini kiriting"})
            if not data.get('contract_start'):
                raise serializers.ValidationError({'contract_start': "Boshlanish sanasini kiriting"})
        return data

    def create(self, validated_data):
        from dateutil.relativedelta import relativedelta
        months = validated_data.get('contract_months')
        start  = validated_data.get('contract_start')
        if months and start:
            validated_data['contract_end'] = start + relativedelta(months=months)
        return super().create(validated_data)


class StaffSalarySerializer(serializers.ModelSerializer):
    staff_name      = serializers.CharField(source='staff.full_name', read_only=True)
    staff_role      = serializers.CharField(source='staff.get_role_display', read_only=True)
    staff_role_key  = serializers.CharField(source='staff.role', read_only=True)
    staff_phone     = serializers.CharField(source='staff.phone', read_only=True)
    contract_type   = serializers.CharField(source='staff.contract_type', read_only=True)
    total_owed      = serializers.SerializerMethodField()

    class Meta:
        model  = StaffSalary
        fields = (
            'id', 'staff', 'staff_name', 'staff_role', 'staff_role_key',
            'staff_phone', 'contract_type', 'company', 'month',
            'calculated_amount', 'paid_amount', 'carry_over', 'total_owed',
            'status', 'is_paid', 'paid_at',
        )
        read_only_fields = ('id', 'company')

    def get_total_owed(self, obj):
        return obj.calculated_amount + obj.carry_over - obj.paid_amount

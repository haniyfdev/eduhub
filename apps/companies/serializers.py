from rest_framework import serializers
from .models import Company, CompanySettings


class CompanySerializer(serializers.ModelSerializer):
    branch_of_name = serializers.CharField(source='branch_of.name', read_only=True)

    class Meta:
        model = Company
        fields = (
            'id', 'name', 'phone', 'address', 'branch_of', 'branch_of_name',
            'description', 'status', 'closed_at', 'created_at',
        )
        read_only_fields = ('id', 'created_at')


class CompanyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ('id', 'name', 'phone', 'address', 'branch_of', 'description')
        read_only_fields = ('id',)


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = (
            'id', 'company', 'billing_type', 'absent_policy',
            'teacher_contract_break_policy', 'archive_billing_type',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'company', 'created_at', 'updated_at')

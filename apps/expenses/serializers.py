from rest_framework import serializers
from .models import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Expense
        fields = (
            'id', 'company', 'category', 'source', 'amount', 'description',
            'expense_date', 'reference_id', 'created_by', 'created_by_name', 'created_at',
        )
        read_only_fields = ('id', 'company', 'source', 'reference_id', 'created_at')


class ExpenseCreateSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Expense
        fields = ('id', 'category', 'amount', 'description', 'expense_date')
        read_only_fields = ('id',)

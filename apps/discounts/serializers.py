from rest_framework import serializers
from .models import Discount


class DiscountSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = Discount
        fields = (
            'id', 'company', 'course', 'course_name', 'name', 'type',
            'value', 'condition', 'status', 'created_at',
        )
        read_only_fields = ('id', 'company', 'created_at')


class DiscountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = ('id', 'course', 'name', 'type', 'value', 'condition')
        read_only_fields = ('id',)

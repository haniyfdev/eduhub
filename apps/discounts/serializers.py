from rest_framework import serializers
from .models import Discount


class DiscountSerializer(serializers.ModelSerializer):
    student_name    = serializers.SerializerMethodField()
    student_phone   = serializers.CharField(source='student.phone', read_only=True)
    course_name     = serializers.CharField(source='course.name', read_only=True)
    course_price    = serializers.DecimalField(source='course.price', max_digits=15, decimal_places=2, read_only=True)
    discount_amount = serializers.SerializerMethodField()
    final_amount    = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Discount
        fields = [
            'id', 'student', 'student_name', 'student_phone',
            'course', 'course_name', 'course_price',
            'percent', 'months', 'start_month', 'end_month',
            'discount_amount', 'final_amount',
            'created_by_name', 'note', 'created_at',
        ]
        read_only_fields = ['id', 'end_month', 'created_at']

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    def get_discount_amount(self, obj):
        return float(obj.course.price) * obj.percent / 100

    def get_final_amount(self, obj):
        return float(obj.course.price) * (1 - obj.percent / 100)

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return ''


class DiscountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = ['student', 'course', 'percent', 'months', 'note']

    def validate_percent(self, value):
        if not 1 <= value <= 100:
            raise serializers.ValidationError("Chegirma 1-100% orasida bo'lishi kerak")
        return value

    def validate_months(self, value):
        if not 1 <= value <= 12:
            raise serializers.ValidationError("Muddat 1-12 oy orasida bo'lishi kerak")
        return value

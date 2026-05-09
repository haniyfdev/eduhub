from rest_framework import serializers
from .models import Debt
 
 
class DebtSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.SerializerMethodField()
    student_second_phone = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
 
    class Meta:
        model = Debt
        fields = (
            'id', 'company', 'student', 'student_name',
            'student_phone', 'student_second_phone', 'group_name',
            'amount', 'due_date', 'status', 'updated_at',
        )
        read_only_fields = ('id', 'company', 'student', 'updated_at')
 
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
 
    def get_student_phone(self, obj):
        return obj.student.phone or ''
 
    def get_student_second_phone(self, obj):
        return obj.student.second_phone or ''
 
    def get_group_name(self, obj):
        membership = obj.student.group_memberships.filter(
            left_at__isnull=True
        ).select_related('group').first()
        return membership.group.display_name if membership else None
 
 
class DebtUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = ('status',)
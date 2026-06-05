from rest_framework import serializers
from .models import Debt


class DebtSerializer(serializers.ModelSerializer):
    student_id           = serializers.CharField(source='group_student.student.id', read_only=True)
    student_name         = serializers.SerializerMethodField()
    student_phone        = serializers.CharField(source='group_student.student.phone', read_only=True)
    student_second_phone = serializers.CharField(source='group_student.student.second_phone', read_only=True)
    student_status       = serializers.CharField(source='group_student.student.status', read_only=True)
    group_name           = serializers.SerializerMethodField()
    group_id             = serializers.CharField(source='group_student.group.id', read_only=True)
    course_id            = serializers.CharField(source='group_student.group.course_id', read_only=True)
    course_name          = serializers.CharField(source='group_student.group.course.name', read_only=True)
    paid_amount          = serializers.SerializerMethodField()
    group_student_status  = serializers.CharField(source='group_student.status', read_only=True)
    group_student_left_at = serializers.DateTimeField(source='group_student.left_at', read_only=True)

    class Meta:
        model = Debt
        fields = (
            'id', 'company', 'group_student',
            'student_id', 'student_name', 'student_phone', 'student_second_phone', 'student_status',
            'group_name', 'group_id', 'course_id', 'course_name',
            'amount', 'paid_amount', 'due_date', 'status', 'updated_at',
            'group_student_status', 'group_student_left_at',
        )
        read_only_fields = ('id', 'company', 'updated_at')

    def get_student_name(self, obj):
        s = obj.group_student.student
        return f"{s.first_name} {s.last_name}"

    def get_group_name(self, obj):
        g = obj.group_student.group
        name = f"{g.number}{(g.gender_type or '').upper()}"
        if obj.group_student.left_at:
            return f"{name} (sobiq)"
        return name

    def get_paid_amount(self, obj):
        from django.db.models import Sum
        from apps.payments.models import Payment
        from decimal import Decimal
        total = Payment.objects.filter(
            group_student=obj.group_student,
            company=obj.company,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return float(total)


class DebtUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = ('status', 'amount')

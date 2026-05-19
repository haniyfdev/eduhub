from rest_framework import serializers
from .models import TeacherSalary, StaffSalary, TeacherWorkLog, StaffKpiRule


class TeacherSalarySerializer(serializers.ModelSerializer):
    teacher_name    = serializers.CharField(source='teacher.user.get_full_name', read_only=True)
    teacher_subject = serializers.CharField(source='teacher.subject', read_only=True)
    salary_type     = serializers.CharField(source='teacher.salary_type', read_only=True)
    salary_percent  = serializers.DecimalField(source='teacher.salary_percent', max_digits=5, decimal_places=2, read_only=True, allow_null=True)
    fixed_amount    = serializers.DecimalField(source='teacher.fixed_amount', max_digits=15, decimal_places=2, read_only=True, allow_null=True)
    per_student_amt = serializers.DecimalField(source='teacher.per_student_amt', max_digits=15, decimal_places=2, read_only=True, allow_null=True)
    group_id          = serializers.SerializerMethodField()
    group_name        = serializers.SerializerMethodField()
    course_name       = serializers.SerializerMethodField()
    student_count     = serializers.SerializerMethodField()
    course_price      = serializers.SerializerMethodField()
    first_active_date = serializers.SerializerMethodField()
    carry_over        = serializers.SerializerMethodField()
    total_owed        = serializers.SerializerMethodField()

    class Meta:
        model = TeacherSalary
        fields = (
            'id', 'teacher', 'teacher_name', 'teacher_subject',
            'group_id', 'group_name', 'course_name',
            'month', 'due_date',
            'salary_type', 'salary_percent', 'fixed_amount', 'per_student_amt',
            'kpi_amount', 'student_count', 'course_price', 'first_active_date',
            'calculated_amount', 'paid_amount', 'carry_over', 'total_owed',
            'status', 'is_paid', 'paid_at',
        )
        read_only_fields = ('id',)

    def get_group_id(self, obj):
        return str(obj.group.id) if obj.group else None

    def get_group_name(self, obj):
        if not obj.group:
            return None
        gender = (obj.group.gender_type or '').upper()
        return f"{obj.group.number}{gender}"

    def get_course_name(self, obj):
        return obj.group.course.name if obj.group and obj.group.course else None

    def get_student_count(self, obj):
        from apps.groups.models import GroupStudent
        if not obj.group:
            return 0
        return GroupStudent.objects.filter(
            group=obj.group,
            left_at__isnull=True,
            student__status='active',
        ).count()

    def get_course_price(self, obj):
        if obj.group and obj.group.course:
            return float(obj.group.course.price)
        return 0

    def get_first_active_date(self, obj):
        from apps.groups.models import GroupStudent
        if not obj.group:
            return None
        gs = GroupStudent.objects.filter(
            group=obj.group,
            student__status__in=['active', 'archived'],
        ).order_by('joined_at').first()
        if not gs:
            return None
        dt = gs.joined_at
        if hasattr(dt, 'date'):
            return dt.date().isoformat()
        return str(dt)

    def get_carry_over(self, obj):
        from django.db.models import Sum
        from decimal import Decimal
        result = TeacherSalary.objects.filter(
            teacher=obj.teacher,
            group=obj.group,
            month__lt=obj.month,
            company=obj.company,
        ).exclude(status='paid').aggregate(
            total_calc=Sum('calculated_amount'),
            total_paid=Sum('paid_amount'),
        )
        total = (result['total_calc'] or Decimal('0')) - (result['total_paid'] or Decimal('0'))
        return max(total, Decimal('0'))

    def get_total_owed(self, obj):
        return obj.calculated_amount + self.get_carry_over(obj)


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

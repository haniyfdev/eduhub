from rest_framework import serializers
from .models import Debt


class DebtSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.SerializerMethodField()
    student_second_phone = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
    group_id = serializers.SerializerMethodField()
    course_id = serializers.SerializerMethodField()
    course_name = serializers.SerializerMethodField()

    class Meta:
        model = Debt
        fields = (
            'id', 'company', 'student', 'student_name',
            'student_phone', 'student_second_phone',
            'group_name', 'group_id', 'course_id', 'course_name',
            'amount', 'due_date', 'status', 'updated_at',
        )
        read_only_fields = ('id', 'company', 'student', 'updated_at')

    def _membership(self, obj):
        """Return (membership, is_former). Active group if exists, else last historical."""
        memberships = list(obj.student.group_memberships.all())
        active = next((m for m in memberships if m.left_at is None), None)
        if active:
            return active, False
        if memberships:
            last = max(memberships, key=lambda m: m.joined_at)
            return last, True
        return None, False

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    def get_student_phone(self, obj):
        return obj.student.phone or ''

    def get_student_second_phone(self, obj):
        return obj.student.second_phone or ''

    def get_group_name(self, obj):
        m, is_former = self._membership(obj)
        if not m:
            return None
        name = f"{m.group.number}{m.group.gender_type}"
        return f"{name} (sobiq)" if is_former else name

    def get_group_id(self, obj):
        m, _ = self._membership(obj)
        return str(m.group.id) if m else None

    def get_course_id(self, obj):
        m, _ = self._membership(obj)
        return str(m.group.course_id) if m else None

    def get_course_name(self, obj):
        m, _ = self._membership(obj)
        if m and m.group.course:
            return m.group.course.name
        return None


class DebtUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Debt
        fields = ('status',)

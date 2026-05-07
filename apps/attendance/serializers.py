from rest_framework import serializers
from .models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    lesson_date = serializers.DateField(source='lesson.date', read_only=True)

    class Meta:
        model = Attendance
        fields = ('id', 'lesson', 'lesson_date', 'student', 'student_name', 'status', 'note')
        read_only_fields = ('id',)

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"


class AttendanceBulkItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['present', 'absent', 'late'])
    note = serializers.CharField(allow_null=True, allow_blank=True, required=False, default='')

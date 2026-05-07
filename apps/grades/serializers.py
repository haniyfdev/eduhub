from rest_framework import serializers
from .models import Grade


class GradeSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    lesson_date = serializers.DateField(source='lesson.date', read_only=True)

    class Meta:
        model = Grade
        fields = ('id', 'lesson', 'lesson_date', 'student', 'student_name', 'score', 'note', 'created_at')
        read_only_fields = ('id', 'created_at')

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"


class GradeListSerializer(serializers.ModelSerializer):
    """Used by the standalone GET /api/v1/grades/ list endpoint."""
    student = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    lesson_date = serializers.DateField(source='lesson.date', read_only=True)

    class Meta:
        model = Grade
        fields = ('id', 'lesson', 'lesson_date', 'student', 'score', 'note', 'created_at', 'group')
        read_only_fields = ('id', 'created_at')

    def get_student(self, obj):
        return {
            'id': str(obj.student.id),
            'first_name': obj.student.first_name,
            'last_name': obj.student.last_name,
        }

    def get_group(self, obj):
        try:
            return {'name': obj.lesson.group.name}
        except Exception:
            return None


class GradeBulkItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    score = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    note = serializers.CharField(allow_null=True, allow_blank=True, required=False, default='')
